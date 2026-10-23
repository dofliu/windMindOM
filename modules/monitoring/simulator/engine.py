import sys
import os
import time
import math
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Callable, Optional, Set
from collections import deque

import numpy as np

# Add parent directory so we can import original modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from wind_model import WindEnvironmentModel
from simulator.grid_model import GridEnvironmentModel
from simulator.physics import TurbinePhysicsModel, FaultEngine
from simulator.physics.fault_engine import FAULT_SCENARIOS, ActiveFault, TestPlanStep
from simulator.physics.wind_field import TurbulenceGenerator, PerTurbineWind
from simulator.modbus_server import ModbusSimServer
from simulator.bulk_events import STATE_CHANGE, BulkEvent
from simulator.farm_events import FarmEvent
from simulator.grid_model import GridOverrideState
from simulator.time_utils import DEFAULT_SITE_TIMEZONE, iso_utc, utc_now


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

    # Farm-level 共用模型的固定 seed（比照下方 _turbulence_gen=42/_per_turbine_wind=99）。
    # 必須落在 add_turbine() 的逐風機 seed 範圍（1..turbine_count，預設上限 14）之外，
    # 否則某個風機的 seed 會跟這個共用模型撞號（WMOM-20260927-01 code review 發現）。
    _GRID_MODEL_SEED = 1042

    def __init__(self, turbine_count: int = 14, base_wind_speed: float = 10.0,
                 turbulence_intensity: float = 0.1,
                 site_timezone: str = DEFAULT_SITE_TIMEZONE):
        # site_timezone：風場時區，日夜 / 季節循環依風場當地時刻（WMOM-20261021-11）
        self.wind_model = WindEnvironmentModel(site_timezone_name=site_timezone)
        self.grid_model = GridEnvironmentModel(seed=self._GRID_MODEL_SEED)
        self.wind_model.turbulence_intensity = turbulence_intensity
        self.turbines: Dict[str, TurbinePhysicsModel] = {}
        self.latest_data: Dict[str, Dict] = {}
        self.history: Dict[str, deque] = {}
        self.history_maxlen = 3600  # ~1 hour at 1Hz

        self.fault_engine = FaultEngine()
        self.modbus_server: Optional[ModbusSimServer] = None
        # 風場事件（風向快速變化，WMOM-20261021-08-b）加在風場風向上的偏移；0 時不套用（健康資料不變）
        self._direction_offset_deg = 0.0

        # Per-turbine wind variation and turbulence
        self._turbulence_gen = TurbulenceGenerator(seed=42)
        self._per_turbine_wind = PerTurbineWind(turbine_count, seed=99)
        # Previous-step yaw misalignment (rad), fed into wake-steering each step
        self._last_yaw_err_rad = np.zeros(turbine_count)
        # Optional sink for "fault caused a PLC trip" (set by generate_bulk; WMOM-20261021-03-b)
        self._on_fault_tripped: Optional[Callable[[str, str, int, datetime], None]] = None

        self._running = False       # Live 自由跑迴圈旗標（_loop / start / stop 專用）
        self._bulk_running = False  # generate_bulk 批次續跑旗標（與 _running 解耦，見 stop_live_loop）
        # generate_bulk 啟動次數：即時模擬的外部讀取端（OPC UA LiveFeeder）據此辨認批次留下的狀態
        self.bulk_runs = 0
        self._thread: Optional[threading.Thread] = None
        # 讓 _loop 每步之間的睡眠可被 stop() 立刻中斷（WMOM-20260720-08 (2)，比照
        # DataBroker._maintenance_wake 同款修法）：不用 time.sleep()，否則 stop() 撞上該次
        # 睡眠時得等它自然結束才能 join。real-time 分支（time_step 睡眠）與 accelerated
        # 分支（wall_sleep 睡眠，WMOM-20260922-01）都靠它中斷。
        self._wake = threading.Event()
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
        self._wake.clear()  # 重入啟動：清掉上次 stop() 設的喚醒旗標
        self._time_step = time_step
        self._thread = threading.Thread(
            target=self._loop, args=(time_step,), daemon=True
        )
        self._thread.start()

    def stop(self):
        """Stop the simulation loop and wait for the background thread to finish."""
        self._running = False
        self._wake.set()  # 立刻喚醒睡眠中的 _loop，讓它在下一次條件檢查就退出
        # 若有同步批次在跑，一併請它停——保留原本「共用 _running 旗標」時 stop() 能中止
        # generate_bulk 的語意（如伺服器關閉時）。stop_live_loop 會在批次「前」呼叫 stop()，
        # 之後 generate_bulk 於進入時再把旗標設回 True，故不衝突。
        self._bulk_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def stop_live_loop(self) -> bool:
        """批次生成前用：停掉 Live 自由跑背景 thread（若在跑），確保它**真的退場**再返回。

        目的：避免 Live thread 與同步的 ``generate_bulk`` (a) 同時 step 同一組物理模型（race）、
        (b) 同時寫同一 SQLite（``database is locked``）。批次的續跑改用獨立的 ``_bulk_running``
        旗標（見 ``generate_bulk``），與 Live 的 ``_running`` **解耦**——故本方法不再把 ``_running``
        設回 True。這修掉一個隱患：若 ``stop()`` 的 ``join(timeout=5)`` 逾時（Live 單步在鎖競爭下
        >5s），舊寫法會把共用的 ``_running`` 設回 True，讓尚未退出的舊 thread「借屍還魂」續跑成
        第二個 writer，而 ``restore_live_loop`` 又會 ``start()`` 一條新 thread → 舊 thread 與其
        SQLite connection 洩漏。改為解耦旗標 + 阻塞式再 join，保證舊 thread 退場後才返回。

        Returns:
            批次前 Live thread 是否在跑（供 ``restore_live_loop`` 決定是否恢復）。
        """
        was_running = self._thread is not None and self._thread.is_alive()
        if was_running:
            self.stop()  # _running=False + join(timeout=5)
            # join(timeout=5) 可能逾時而 thread 仍活著。此時 _running 已為 False，_loop 會在
            # 下一次迴圈條件檢查時退出——阻塞式再 join 一次確保它真的結束，避免 restore_live_loop
            # 又 start() 新 thread 造成舊 thread 洩漏。批次端點本就可能跑數分鐘，這裡多等可接受。
            if self._thread is not None:
                self._thread.join()
        return was_running

    def restore_live_loop(self, was_running: bool, time_step: float = 1.0) -> None:
        """``generate_bulk`` 後恢復 Live 自由跑（若批次前在跑）。

        Args:
            was_running: 批次前 Live thread 是否在跑（``stop_live_loop`` 的回傳值）。
            time_step: 恢復 Live 用的 step 秒數（僅在 ``was_running`` 為 True 時使用）。
        """
        # 批次期間 _running 一直是 False（stop_live_loop 停掉、generate_bulk 只動 _bulk_running），
        # 故這裡不需再手動清 _running；只在原本在跑時重新 start() 一條 Live thread。
        if was_running:
            self.start(time_step=time_step)

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
        if self._direction_offset_deg:
            wind_direction = (wind_direction + self._direction_offset_deg) % 360.0
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

            turbine_faults = [f for f in self.fault_engine.active_faults if f.turbine_id == tid]
            model.active_faults = [
                {
                    "scenario_id": fault.scenario_id,
                    "severity": fault.severity,
                    "tripped": fault.tripped,
                }
                for fault in turbine_faults
            ]
            # Reset ≠ repair (WMOM-20260719-01): once a fault has caused a PLC trip the
            # turbine stays down until maintenance clears the fault. A restart inhibit,
            # not a fresh emergency stop every step (that made TurSt oscillate 7↔3)
            # (WMOM-20261021-03-b).
            lock = any(f.tripped for f in turbine_faults)
            if model.maintenance_lock and not lock:
                # 故障被維護清除＝修好後技師復位：清 PLC 每小時跳機計數與封鎖。不論走哪條清除路徑
                # （/api/faults/clear 不帶機組、情境批次、測試計畫都不會 model.reset()），否則
                # 一小時內第二次跳機留下的封鎖（A039）會讓已修好的機組永遠停機
                model.plc.maintenance_release(model._sim_time)
            model.maintenance_lock = lock

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

            if turbine_faults:
                self._link_faults_to_plc(tid, model, turbine_faults, sim_time)

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

        模擬時間一律 tz-aware UTC（WMOM-20261021-03-c）。
        """
        sim_time = utc_now()

        while self._running:
            try:
                ts = self.wind_model.time_scale
                if ts <= 1.0:
                    # Real-time mode: 1 step per wall-clock second
                    sim_time = utc_now()
                    readings = self._run_one_step(sim_time, time_step)
                    for cb in self._callbacks:
                        try:
                            cb(readings)
                        except Exception:
                            pass
                    self._wake.wait(time_step)
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

                    # 比照 real-time 分支（見上）：accelerated 模式的 wall_sleep 也要能被
                    # stop() 立刻中斷，否則高倍速模式下 stop() 得等到這次 wall_sleep 自然
                    # 結束才能 join()（WMOM-20260720-08 review 已知留待處理的 open question）。
                    self._wake.wait(wall_sleep)

            except Exception as e:
                print(f"[Simulator] Error: {e}")
                time.sleep(1)

    def _link_faults_to_plc(self, tid: str, model: TurbinePhysicsModel,
                            faults: List[ActiveFault], sim_time: datetime) -> None:
        """把 PLC 判定結果回寫到故障：預期碼中目前成立者 → ``active_alarms``；PLC 以預期跳機碼
        跳機 → ``FaultEngine.mark_tripped``（WMOM-20261021-03-b）。

        Args:
            tid: 機組 ID。
            model: 該機組物理模型（含 ``plc``）。
            faults: 該機組的 active faults。
            sim_time: 本步模擬時間。
        """
        active = model.plc.active_codes()
        new_trips = set(model.plc.last_trip_codes)
        for fault in faults:
            scenario = FAULT_SCENARIOS.get(fault.scenario_id)
            if scenario is None:
                continue
            fault.active_alarms = [a for a in scenario.alarm_codes if a["code"] in active]
            if fault.tripped:
                continue
            trip_codes = [
                a["code"] for a in scenario.alarm_codes
                if a["type"] in ("T1", "T2") and a["code"] in new_trips
            ]
            if trip_codes and self.fault_engine.mark_tripped(tid, fault.scenario_id, trip_codes[0]):
                if self._on_fault_tripped is not None:
                    self._on_fault_tripped(tid, fault.scenario_id, trip_codes[0], sim_time)

    def start_clean_scenario(self) -> List[str]:
        """命名情境 / 測試計畫開始前：清掉故障，並重設帶著 Live 殘留狀態的機組。

        殘留狀態＝PLC 有成立中的警報（含自動重啟封鎖 A039）或鎖存的跳機、維護鎖、停機進行中；其餘機組只清
        PLC 的每小時跳機計數。否則情境開頭
        會出現沒有對應 ``trip`` 的 ``trip_cleared`` / ``operator_reset`` 或莫名停機，標準答案卻把那台機組列為
        健康（盲測資料與答案不一致）。乾淨的機組不重設（不動 RNG 序列：全新 simulator 生成的資料不變）。

        Returns:
            被重設的機組 ID。
        """
        self.fault_engine.clear()
        reset: List[str] = []
        for tid, model in self.turbines.items():
            if model.maintenance_lock or model.plc.active_codes() or model.tur_state in (7, 9):
                model.reset()
                reset.append(tid)
            else:
                # 乾淨的機組只清每小時跳機計數（不動 RNG、不送事件）：Live 一小時內自動恢復過的跳機
                # 不能讓情境的第一次同碼跳機就送 A039（WMOM-20261022-02 code review S1）
                model.plc.clear_trip_counts()
        return reset

    def generate_bulk(self, duration_hours: float, time_step: float = 10.0,
                      callback: Optional[Callable[[List[Dict]], None]] = None,
                      progress_callback: Optional[Callable[[float, float], None]] = None,
                      fault_schedule: Optional[List[TestPlanStep]] = None,
                      on_fault_injected: Optional[Callable[[TestPlanStep, datetime], None]] = None,
                      on_fault_tripped: Optional[Callable[[str, str, int, datetime], None]] = None,
                      on_events: Optional[Callable[[List[BulkEvent]], None]] = None,
                      farm_events: Optional[List[FarmEvent]] = None,
                      on_farm_event: Optional[Callable[[FarmEvent, datetime, datetime], None]] = None) -> int:
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
            on_fault_tripped: 選填。PLC 以故障的預期跳機碼使機組跳機、故障轉為 tripped 的當下，以
                ``(turbine_id, scenario_id, trip_code, sim_time)`` 回呼，讓呼叫端把跳機寫成
                事件（情境掛載依此判定 FAULT，WMOM-20261021-03-b）。
            on_events: 選填。每個輸出步結束時，以本步（所有物理子步）收集到的可觀測事件回呼：
                PLC 事件（警報 / 跳機 / 復位 / 資訊）與運轉狀態轉換，時間戳為模擬時間
                （WMOM-20261021-04）。不給時事件照舊丟棄。收集只讀狀態、不改物理結果。
            farm_events: 選填。風場層級事件（電網擾動、風向快速變化，WMOM-20261021-08-b），各於自身
                ``offset_seconds``（相對批次起點）開始、持續 ``duration_s``，逐個物理子步套用。電網事件期間
                覆寫風場電網模型，結束後恢復批次開始前的狀態；風向偏移在批次結束時歸零。
            on_farm_event: 選填。每個風場事件開始時，以 ``(event, 開始模擬時間, 結束模擬時間)`` 回呼
                （標準答案據此標 nuisance case）。

        Returns:
            Total number of readings generated
        """
        total_steps = int(duration_hours * 3600 / time_step)
        sim_time = utc_now()
        total_readings = 0
        report_interval = max(1, total_steps // 100)  # report every 1%

        # 每個輸出步拆成穩定的物理子步（≤_MAX_PHYSICS_DT），避免大 time_step 令 rotor
        # speed 數值發散（WMOM-20260718-10）。輸出仍以 time_step 為節奏（只落地最後一子步）。
        n_sub = max(1, math.ceil(time_step / _MAX_PHYSICS_DT))
        sub_dt = time_step / n_sub

        # 依注入時間排序；sched_idx 指向下一支待注入的故障。
        schedule = sorted(fault_schedule or [], key=lambda s: s.offset_seconds)
        sched_idx = 0
        # 風場事件：開始過的事件（回呼一次）與批次開始前的電網覆寫狀態（事件結束 / 批次結束時恢復）
        events_sorted = sorted(farm_events or [], key=lambda e: e.offset_seconds)
        started_events: Set[int] = set()
        grid_state = self.grid_model.snapshot()
        grid_overridden = False
        # 最後一個事件結束、狀態也復原後就不必每個子步掃一遍
        farm_events_end_s = max((e.end_seconds for e in events_sorted), default=0.0)

        # 批次續跑旗標與 Live 的 _running **解耦**：即使 Live 未在跑（stop_live_loop 後 _running
        # 為 False）批次仍應執行；且「停 Live」與「跑批次」不再共用旗標互相干擾（見 stop_live_loop
        # 的 borrow-corpse 隱患）。stop() 會清此旗標以保留「關閉時中止批次」的語意。
        self._bulk_running = True
        self.bulk_runs += 1
        prev_on_fault_tripped = self._on_fault_tripped
        self._on_fault_tripped = on_fault_tripped
        # 狀態轉換偵測的前一個 WTUR_TurSt（第一個子步只建立基準、不出事件）
        last_states: Dict[str, int] = {}
        if on_events is not None:
            # 批次開始前佇列裡的 PLC 事件屬於 Live（broker 已處理或停 Live 前的殘留），不算本批
            for model in self.turbines.values():
                model.plc.drain_events()
        try:
            for step_i in range(total_steps):
                if not self._bulk_running:
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
                # 事件則每個子步都收（狀態轉換可能只維持一個子步）。
                readings: List[Dict] = []
                step_events: List[BulkEvent] = []
                for sub_i in range(n_sub):
                    if events_sorted and (elapsed_seconds + sub_i * sub_dt <= farm_events_end_s
                                          or grid_overridden or self._direction_offset_deg):
                        grid_overridden = self._apply_farm_events(
                            events_sorted, elapsed_seconds + sub_i * sub_dt, sim_time, started_events,
                            grid_state, grid_overridden, on_farm_event)
                    sim_time += timedelta(seconds=sub_dt)
                    readings = self._run_one_step(sim_time, sub_dt)
                    if on_events is not None:
                        step_events.extend(self._collect_bulk_events(sim_time, readings, last_states))
                total_readings += len(readings)

                if callback:
                    callback(readings)
                if step_events:
                    on_events(step_events)

                if progress_callback and step_i % report_interval == 0:
                    current_hours = step_i * time_step / 3600
                    progress_callback(current_hours, duration_hours)
        finally:
            self._bulk_running = False
            self._on_fault_tripped = prev_on_fault_tripped
            if events_sorted:
                self.grid_model.restore(grid_state)
                self._direction_offset_deg = 0.0
            # 不收事件（on_events 為 None）時丟掉佇列裡的批次事件，否則 Live 恢復後 broker 會把
            # 它們當成「剛剛發生」的事件寫入；收事件時這裡只會是空的
            for model in self.turbines.values():
                model.plc.drain_events()

        return total_readings

    def _apply_farm_events(self, events: List[FarmEvent], elapsed_s: float, sim_time: datetime,
                           started: Set[int], grid_state: GridOverrideState, grid_overridden: bool,
                           on_farm_event: Optional[Callable[[FarmEvent, datetime, datetime], None]]) -> bool:
        """套用 ``elapsed_s`` 時進行中的風場事件（一個物理子步開始前）。

        電網：電壓驟降取最深的、頻率越界加總；沒有進行中的電網事件時恢復批次開始前的覆寫狀態。風向：進行中
        擺動的偏移加總。事件第一次進行時回呼 ``on_farm_event``。

        Args:
            events: 依開始時間排序的風場事件。
            elapsed_s: 相對批次起點的秒數（本子步開始時）。
            sim_time: 本子步開始時的模擬時刻。
            started: 已回呼過的事件索引（就地更新）。
            grid_state: 批次開始前的電網覆寫狀態。
            grid_overridden: 目前電網是否被事件覆寫。
            on_farm_event: 事件開始回呼。

        Returns:
            套用後電網是否被事件覆寫。
        """
        active = [(i, e) for i, e in enumerate(events) if e.is_active(elapsed_s)]
        for i, event in active:
            if i not in started:
                started.add(i)
                if on_farm_event is not None:
                    on_farm_event(event, sim_time, sim_time + timedelta(seconds=event.duration_s))
        grid = self.grid_model
        dips = [e.magnitude for _, e in active if e.kind == "grid_voltage_dip"]
        freq_shift = [e.magnitude for _, e in active if e.kind == "grid_frequency_excursion"]
        if dips or freq_shift:
            voltage = grid.base_voltage_v * min(dips) if dips else grid_state[1]
            frequency = grid.base_frequency_hz + sum(freq_shift) if freq_shift else grid_state[0]
            grid.apply_event_override(frequency, voltage)
            grid_overridden = True
        elif grid_overridden:
            grid.restore(grid_state)
            grid_overridden = False
        self._direction_offset_deg = sum(e.wind_direction_offset(elapsed_s) for _, e in active)
        return grid_overridden

    def _collect_bulk_events(self, sim_time: datetime, readings: List[Dict],
                             last_states: Dict[str, int]) -> List[BulkEvent]:
        """收集一個物理子步的可觀測事件（WMOM-20261021-04）。

        PLC 事件的時刻＝本子步模擬時間往回推（事件 ``sim_time`` 與機組 ``_sim_time`` 同一時間軸，
        與 broker Live 路徑的 ``_plc_event_timestamp`` 相同換算）；狀態轉換記在本子步時刻，排在
        同機組的 PLC 事件之後（跳機事件先於它造成的停機狀態）。

        Args:
            sim_time: 本子步結束時的模擬時刻（tz-aware UTC）。
            readings: 本子步各機組的輸出。
            last_states: 各機組上一個子步的 ``WTUR_TurSt``（就地更新）。

        Returns:
            本子步的事件（依機組、PLC 事件在前）。
        """
        events: List[BulkEvent] = []
        for reading in readings:
            tid = reading["turbine_id"]
            model = self.turbines[tid]
            for plc_event in model.plc.drain_events():
                lag_s = max(0.0, float(model._sim_time) - plc_event.sim_time)
                events.append(BulkEvent(
                    timestamp=sim_time - timedelta(seconds=lag_s),
                    turbine_id=tid,
                    kind=plc_event.kind,
                    plc_event=plc_event,
                ))
            state = int(reading["scada"].get("WTUR_TurSt", 0) or 0)
            previous = last_states.get(tid)
            if previous is not None and previous != state:
                events.append(BulkEvent(
                    timestamp=sim_time,
                    turbine_id=tid,
                    kind=STATE_CHANGE,
                    from_state=previous,
                    to_state=state,
                    shutdown_cause=model.get_control_status().get("shutdown_cause"),
                ))
            last_states[tid] = state
        return events

    @staticmethod
    def _scada_to_output(tid: str, timestamp: datetime,
                         scada: Dict[str, float],
                         wind_speed: float, wind_direction: float) -> Dict:
        """Convert flat SCADA dict to the nested output format expected by data_broker.

        ``timestamp`` 以固定格式的 UTC ISO 字串輸出（naive 值視為本地時間，WMOM-20261021-03-c）。
        """
        return {
            'timestamp': iso_utc(timestamp),
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

    @property
    def is_bulk_running(self) -> bool:
        """``generate_bulk`` 是否正在跑（期間 ``latest_data`` / PLC 狀態是批次的模擬時間，不是即時）。"""
        return self._bulk_running

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
