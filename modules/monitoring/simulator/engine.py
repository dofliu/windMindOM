import sys
import os
import time
import math
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Callable, Optional
from collections import deque

import numpy as np

# Add parent directory so we can import original modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from wind_model import WindEnvironmentModel
from simulator.grid_model import GridEnvironmentModel
from simulator.physics import TurbinePhysicsModel, FaultEngine
from simulator.physics.fault_engine import TestPlanStep
from simulator.physics.wind_field import TurbulenceGenerator, PerTurbineWind
from simulator.modbus_server import ModbusSimServer


def _zero_non_finite(scada: Dict[str, float]) -> List[str]:
    """把 SCADA dict 內的非有限數值（inf/nan）就地歸零，回傳被歸零的 tag 名清單。

    非有限值（通常源自異常風機規格導致上游物理發散）會打爆 Modbus 的 int() 轉換、
    JSON 序列化與前端 recharts，故在此單一 choke point 攔下——讓一顆壞 tag 不至於
    弄垮整個模擬迴圈（WMOM-20260718-09）。非數值 tag（如字串）略過。
    """
    hit: List[str] = []
    for k, v in scada.items():
        try:
            if not math.isfinite(v):
                scada[k] = 0.0
                hit.append(k)
        except (TypeError, ValueError):
            pass  # 非數值 tag（字串等）→ 跳過
    return hit


# 物理積分的穩定上限：實測 dt≤5s 穩定、dt≥8s rotor speed 會數值發散→inf（WMOM-20260718-10）。
# generate_bulk 用較大 time_step（10/60s）換速度，故須把每個輸出步拆成 ≤此值的子步跑物理。
_MAX_PHYSICS_DT = 5.0


class WindFarmSimulator:
    """Wind farm simulator engine — produces realistic SCADA data via callbacks.

    Uses the independent physics model (simulator/physics/) for each turbine,
    plus a shared FaultEngine for fault injection across the farm.
    Optionally exposes data via Modbus TCP server.
    """

    def __init__(self, turbine_count: int = 14, base_wind_speed: float = 10.0,
                 turbulence_intensity: float = 0.1):
        self.wind_model = WindEnvironmentModel()
        self.grid_model = GridEnvironmentModel()
        self.wind_model.turbulence_intensity = turbulence_intensity
        self.turbines: Dict[str, TurbinePhysicsModel] = {}
        self.latest_data: Dict[str, Dict] = {}
        self.history: Dict[str, deque] = {}
        self.history_maxlen = 3600  # ~1 hour at 1Hz

        self.fault_engine = FaultEngine()
        self.modbus_server: Optional[ModbusSimServer] = None

        # Per-turbine wind variation and turbulence
        self._turbulence_gen = TurbulenceGenerator(seed=42)
        self._per_turbine_wind = PerTurbineWind(turbine_count, seed=99)
        # Previous-step yaw misalignment (rad), fed into wake-steering each step
        self._last_yaw_err_rad = np.zeros(turbine_count)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: List[Callable] = []
        self._lock = threading.Lock()
        self._warned_non_finite = False  # non-finite SCADA 警告只印一次

        # Initialize turbines
        for i in range(1, turbine_count + 1):
            tid = f"WT{i:03d}"
            self.add_turbine(tid, seed=i)

    def add_turbine(self, turbine_id: str, seed: Optional[int] = None):
        """Register a new turbine physics model with optional deterministic seed."""
        self.turbines[turbine_id] = TurbinePhysicsModel(seed=seed)
        self.latest_data[turbine_id] = {}
        self.history[turbine_id] = deque(maxlen=self.history_maxlen)

    def on_data(self, callback: Callable[[List[Dict]], None]):
        """Register a callback that receives a list of turbine readings each step."""
        self._callbacks.append(callback)

    def start(self, time_step: float = 1.0):
        """Start the simulation loop in a background thread at the given timestep."""
        if self._running:
            return
        self._running = True
        self._time_step = time_step
        self._thread = threading.Thread(
            target=self._loop, args=(time_step,), daemon=True
        )
        self._thread.start()

    def stop(self):
        """Stop the simulation loop and wait for the background thread to finish."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    @property
    def time_scale(self) -> float:
        """Current time acceleration factor. 1.0=real-time, 60=1min/s."""
        return self.wind_model.time_scale

    @time_scale.setter
    def time_scale(self, value: float):
        """Set time acceleration factor (clamped to minimum 1.0)."""
        self.wind_model.time_scale = max(1.0, value)

    def _run_one_step(self, sim_time: datetime, time_step: float):
        """Execute one physics timestep for all turbines. Returns readings list."""
        base_wind = self.wind_model.get_wind_speed(sim_time)
        wind_direction = self.wind_model.get_wind_direction(sim_time)
        ambient_temp = self.wind_model.get_ambient_temp(sim_time)
        ambient_humidity = self.wind_model.get_ambient_humidity(sim_time)
        grid_frequency = self.grid_model.get_frequency(sim_time)
        grid_voltage = self.grid_model.get_voltage(sim_time)

        # Atmospheric stability couples diurnal cycle to shear α and TI (#99).
        # Compute the stability score once; pass it to the shear / TI getters
        # so we don't mutate the weather RNG state multiple times per step.
        # Manual overrides return neutral values automatically.
        atm_stability = self.wind_model.get_atmospheric_stability(sim_time)
        shear_alpha = self.wind_model.get_shear_exponent(sim_time, stability=atm_stability)
        ti_mult = self.wind_model.get_turbulence_multiplier(sim_time, stability=atm_stability)
        effective_ti = max(0.0, self.wind_model.turbulence_intensity * ti_mult)

        # Air density ρ(T, RH, P) from ideal gas law + Magnus vapor correction
        # (#101, #106). Ambient pressure varies with synoptic weather state
        # (frontal passages ±15 hPa), adding another ±1.5% ρ time variability.
        # Shared by all turbines (physical fact: same airmass across the farm).
        ambient_pressure = self.wind_model.get_ambient_pressure(sim_time)
        air_density = self.wind_model.get_air_density(
            sim_time, ambient_temp=ambient_temp, humidity=ambient_humidity,
            pressure_pa=ambient_pressure,
        )

        # `atm_stability` modulates the AR(1) integral length scale L_u
        # (#115) so farm-wide wind autocorrelation matches the ABL state.
        turb_component = self._turbulence_gen.step(
            base_wind, effective_ti, time_step, stability=atm_stability,
        )
        farm_wind = max(0, base_wind + turb_component)

        # Feed previous-step yaw misalignments back into the wind field so the
        # wake-steering deflection (Bastankhah 2016) is ready before we compute
        # per-turbine wake factors this step.
        self._per_turbine_wind.set_yaw_misalignments(self._last_yaw_err_rad)

        # Advance wind field: per-turbine turbulence + event propagation.
        # `atm_stability` modulates Bastankhah k* (#109) so the wake persists
        # longer on stable nights and recovers faster on convective afternoons.
        self._per_turbine_wind.step(
            farm_wind, wind_direction,
            effective_ti, time_step,
            atm_stability=atm_stability,
        )

        # FaultEngine.step() advances severity progression and alarm tracking.
        # Tag offsets are no longer used — all fault effects flow through
        # _get_fault_physics() inside each TurbinePhysicsModel.
        self.fault_engine.step(dt=time_step)

        readings = []
        for tid, model in self.turbines.items():
            idx = int(tid[2:]) - 1
            local_wind = self._per_turbine_wind.get_local_wind(farm_wind, idx)
            local_direction = self._per_turbine_wind.get_local_direction(wind_direction, idx)
            local_ti_multiplier = self._per_turbine_wind.get_local_ti_multiplier(idx)
            wake_deficit = self._per_turbine_wind.get_wake_deficit(idx)
            wake_meander_m = self._per_turbine_wind.get_wake_meander_offset(idx)
            wake_yaw_defl_m = self._per_turbine_wind.get_wake_yaw_deflection_offset(idx)
            wake_added_ti = self._per_turbine_wind.get_wake_added_ti(idx)

            model.active_faults = [
                {
                    "scenario_id": fault.scenario_id,
                    "severity": fault.severity,
                    "tripped": fault.tripped,
                }
                for fault in self.fault_engine.active_faults
                if fault.turbine_id == tid
            ]

            for fault in self.fault_engine.active_faults:
                if fault.turbine_id == tid and fault.tripped:
                    model.cmd_emergency_stop(cause=f"fault:{fault.scenario_id}")

            scada_output = model.step(
                local_wind,
                local_direction,
                ambient_temp,
                time_step,
                grid_frequency_ref=grid_frequency,
                grid_voltage_ref=grid_voltage,
                ambient_humidity_pct=ambient_humidity,
                local_ti_multiplier=local_ti_multiplier,
                wake_deficit=wake_deficit,
                wake_meander_offset_m=wake_meander_m,
                wake_yaw_deflection_m=wake_yaw_defl_m,
                wake_added_ti=wake_added_ti,
                wind_shear_exp_base=shear_alpha,
                atm_stability=atm_stability,
                air_density=air_density,
                ambient_pressure_pa=ambient_pressure,
                effective_ti=effective_ti,
            )

            # 防呆：非有限值（inf/nan）歸零，避免打爆 Modbus int() / JSON / 前端圖表。
            # 通常源自異常風機規格；印一次警告讓根因可見（WMOM-20260718-09）。
            bad_tags = _zero_non_finite(scada_output)
            if bad_tags and not self._warned_non_finite:
                print(
                    f"[Simulator] WARNING: non-finite SCADA zeroed on {tid}: {bad_tags[:6]} "
                    f"— 檢查該風場的風機規格（rotor_diameter / 額定等欄位是否為 0 或空）"
                )
                self._warned_non_finite = True

            # Capture yaw_error (deg) for this step; fed back next step to drive
            # wake-steering deflection.
            yaw_err_deg = float(scada_output.get("WYAW_YwVn1AlgnAvg5s", 0.0))
            self._last_yaw_err_rad[idx] = math.radians(yaw_err_deg)

            output = self._scada_to_output(tid, sim_time, scada_output, local_wind, wind_direction)

            with self._lock:
                self.latest_data[tid] = output
                self.history[tid].append(output)

            readings.append(output)

            if self.modbus_server and self.modbus_server.is_running:
                self.modbus_server.update_turbine(tid, scada_output)

        return readings

    def _loop(self, time_step: float):
        """Main simulation loop. Supports time_scale for accelerated simulation.

        time_scale=1: real-time (1 physics second per wall second)
        time_scale=60: 60 physics seconds per wall second (1 min/s)
        time_scale=3600: 1 hour of simulation per wall second
        """
        sim_time = datetime.now()

        while self._running:
            try:
                ts = self.wind_model.time_scale
                if ts <= 1.0:
                    # Real-time mode: 1 step per wall-clock second
                    sim_time = datetime.now()
                    readings = self._run_one_step(sim_time, time_step)
                    for cb in self._callbacks:
                        try:
                            cb(readings)
                        except Exception:
                            pass
                    time.sleep(time_step)
                else:
                    # Accelerated mode: run multiple physics steps per wall second
                    # Each wall second advances sim_time by time_scale seconds
                    steps_per_tick = int(ts)
                    wall_sleep = max(0.1, time_step / ts * steps_per_tick)

                    for _ in range(steps_per_tick):
                        if not self._running:
                            break
                        sim_time += timedelta(seconds=time_step)
                        readings = self._run_one_step(sim_time, time_step)

                    # Only fire callbacks once per wall-tick (with latest readings)
                    for cb in self._callbacks:
                        try:
                            cb(readings)
                        except Exception:
                            pass

                    time.sleep(wall_sleep)

            except Exception as e:
                print(f"[Simulator] Error: {e}")
                time.sleep(1)

    def generate_bulk(self, duration_hours: float, time_step: float = 10.0,
                      callback: Optional[Callable[[List[Dict]], None]] = None,
                      progress_callback: Optional[Callable[[float, float], None]] = None,
                      fault_schedule: Optional[List[TestPlanStep]] = None,
                      on_fault_injected: Optional[Callable[[TestPlanStep, datetime], None]] = None) -> int:
        """Generate bulk historical data without real-time waiting.

        Runs the full physics simulation at maximum speed, writing data
        via callbacks. Useful for generating months of training data.

        Args:
            duration_hours: How many hours of simulated data to generate
            time_step: Physics step interval (10s default for storage efficiency)
            callback: Called with readings each step (same as on_data callbacks)
            progress_callback: Called with (current_hours, total_hours) periodically
            fault_schedule: 選填。一組 ``TestPlanStep``，各於自身 ``offset_seconds``
                （相對本次批次起點）被注入。讓 Scenario 模式的批次資料集能包含
                「在指定 sim-time 才發生」的故障（WMOM-20260718-03, DEC-20260718-01）。
                本方法不會先清除既有 active fault——要乾淨情境請先 ``fault_engine.clear()``。
            on_fault_injected: 選填。每支故障**成功注入**的當下，以
                ``(step, sim_time)`` 回呼（``sim_time`` 為該注入的模擬時間）。讓呼叫端
                以正確的模擬時間戳持久化故障事件（如 ``broker.record_event(timestamp=...)``），
                使事件標記與批次資料的時間軸對齊、情境可重現。未知 scenario（``inject``
                回 False）不會觸發此回呼。

        Returns:
            Total number of readings generated
        """
        total_steps = int(duration_hours * 3600 / time_step)
        sim_time = datetime.now()
        total_readings = 0
        report_interval = max(1, total_steps // 100)  # report every 1%

        # 每個輸出步拆成穩定的物理子步（≤_MAX_PHYSICS_DT），避免大 time_step 令 rotor
        # speed 數值發散（WMOM-20260718-10）。輸出仍以 time_step 為節奏（只落地最後一子步）。
        n_sub = max(1, math.ceil(time_step / _MAX_PHYSICS_DT))
        sub_dt = time_step / n_sub

        # 依注入時間排序；sched_idx 指向下一支待注入的故障。
        schedule = sorted(fault_schedule or [], key=lambda s: s.offset_seconds)
        sched_idx = 0

        for step_i in range(total_steps):
            if not self._running:
                break

            # 注入所有已到 offset 的排程故障（可能同一 step 注入多支）。
            # sim_time 此刻尚未加上本步 dt，正是此故障的注入模擬時間。
            elapsed_seconds = step_i * time_step
            while sched_idx < len(schedule) and schedule[sched_idx].offset_seconds <= elapsed_seconds:
                fstep = schedule[sched_idx]
                injected = self.fault_engine.inject(
                    scenario_id=fstep.scenario_id,
                    turbine_id=fstep.turbine_id,
                    severity_rate=fstep.severity_rate,
                    initial_severity=fstep.initial_severity,
                )
                # 僅在真的注入成功時回呼（inject 對未知 scenario 回 False 且不注入）。
                if injected and on_fault_injected is not None:
                    on_fault_injected(fstep, sim_time)
                sched_idx += 1

            # 以穩定子步推進物理；只有最後一子步的 readings 落地（輸出節奏＝time_step）。
            readings: List[Dict] = []
            for _ in range(n_sub):
                sim_time += timedelta(seconds=sub_dt)
                readings = self._run_one_step(sim_time, sub_dt)
            total_readings += len(readings)

            if callback:
                callback(readings)

            if progress_callback and step_i % report_interval == 0:
                current_hours = step_i * time_step / 3600
                progress_callback(current_hours, duration_hours)

        return total_readings

    @staticmethod
    def _scada_to_output(tid: str, timestamp: datetime,
                         scada: Dict[str, float],
                         wind_speed: float, wind_direction: float) -> Dict:
        """Convert flat SCADA dict to the nested output format expected by data_broker."""
        return {
            'timestamp': timestamp.isoformat(),
            'turbine_id': tid,
            'operational_state': _tur_state_to_str(int(scada.get("WTUR_TurSt", 1))),
            'wind_speed': wind_speed,
            'wind_direction': wind_direction,
            'scada': scada,  # Full SCADA tags dict
            'rotor': {
                'rotor_speed': scada.get("WROT_RotSpd", 0),
                'rotor_torque': 0,
            },
            'pitch_angle': scada.get("WROT_PtAngValBl1", 0),
            'gearbox': {
                'temperature': scada.get("WNAC_NacTmp", 40),
                'vibration': scada.get("WNAC_VibMsNacXDir", 0),
            },
            'generator': {
                'power': scada.get("WTUR_TotPwrAt", 0) * 1000,  # kW → W
                'voltage': scada.get("WGEN_GnVtgMs", 0),
                'current': scada.get("WGEN_GnCurMs", 0),
                'temperature': scada.get("WGEN_GnStaTmp1", 45),
                'frequency': scada.get("WCNV_CnvGnFrq", 0),
            },
            'yaw': {
                'yaw_angle': scada.get("WYAW_YwVn1AlgnAvg5s", 0),
                'yaw_error': scada.get("WYAW_YwVn1AlgnAvg5s", 0),
            },
            'hydraulic': {
                'pressure': scada.get("WYAW_YwBrkHyPrs", 0),
            },
            'total_power': scada.get("WTUR_TotPwrAt", 0) * 1000,  # kW → W
        }

    def get_current_data(self) -> Dict[str, Dict]:
        """Return the latest SCADA output for all turbines (thread-safe snapshot)."""
        with self._lock:
            return dict(self.latest_data)

    def get_turbine_data(self, turbine_id: str) -> Optional[Dict]:
        """Return the latest SCADA output for a single turbine, or None."""
        with self._lock:
            return self.latest_data.get(turbine_id)

    def get_history(self, turbine_id: str, limit: int = 100) -> List[Dict]:
        """Return the most recent *limit* in-memory trend samples for a turbine."""
        with self._lock:
            h = self.history.get(turbine_id, deque())
            return list(h)[-limit:]

    @property
    def is_running(self) -> bool:
        """Whether the simulation loop is currently active."""
        return self._running

    @property
    def turbine_ids(self) -> List[str]:
        """Ordered list of all turbine IDs in the farm."""
        return list(self.turbines.keys())


def _tur_state_to_str(state: int) -> str:
    """Map Bachmann TurState (1-9) to internal state string."""
    mapping = {
        1: "IDLE",       # Shutdown
        2: "IDLE",       # Standby
        3: "IDLE",       # Wait Restart
        4: "STARTING",   # Pre-Production
        5: "STARTING",   # Start Production
        6: "RUNNING",    # Production
        7: "STOPPING",   # Shutdown (in progress)
        8: "STARTING",   # Restart
        9: "STOPPING",   # Normal Stop
    }
    return mapping.get(state, "IDLE")
