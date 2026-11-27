"""Z72 例行巡檢的檢查清單（WMOM-20261126-05，DEC-20261127-04）。

例行巡檢卡（``briefing.build_inspection_card``）照這份清單排順序：證據多的往前，沒有證據的維持原順序。

- **原訂順序**是技師上塔的路線：塔底（變頻器與冷卻水、變壓器、電網）→ 偏航平台 → 機艙（通風、發電機、
  主軸承、轉速量測）→ 機艙頂（風速計、風向標）→ 輪轂（變槳）→ 葉片（目視）。
- **每一項看哪些量測**（``tags``）是手冊層級的知識：這個部件有哪些 SCADA 量測。**每一項對應哪些事件碼**不是
  手寫的：由 PLC 的判定規則推出來（事件碼的主要量測落在哪一項，``briefing.related_tags``），少數規則的主要
  量測不在這個部件上的另外列（``extra_codes``）。都不讀故障情境。
- ``components`` 是這一項涵蓋的部件（``shared/data/rag_assistant_vocabulary.json`` 的 component id），**只給
  評分用**（把答案裡故障的部件對到清單的哪一項），不進卡片。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class InspectionItem:
    """清單上的一項。

    Attributes:
        id: 項目 ID。
        label_zh: 中文名稱。
        label_en: 英文名稱。
        tags: 這一項看的 SCADA 量測（tag id）。
        components: 涵蓋的部件（評分用）。
        extra_codes: 主要量測不在 ``tags`` 裡、但屬於這一項的事件碼。
    """

    id: str
    label_zh: str
    label_en: str
    tags: Tuple[str, ...]
    components: Tuple[str, ...]
    extra_codes: Tuple[int, ...] = ()


CHECKLIST: Tuple[InspectionItem, ...] = (
    InspectionItem("converter_cooling", "變頻器與冷卻水系統", "Converter and cooling water",
                   ("WCNV_IGCTWtrTmp", "WCNV_IGCTWtrPres1", "WCNV_IGCTWtrPres2", "WCNV_IGCTWtrCond",
                    "WCNV_CnvCabinTmp"),
                   ("converter_cooling_system",)),
    InspectionItem("transformer", "變壓器", "Transformer", ("WGDC_TrfCoreTmp",), ("transformer",)),
    InspectionItem("grid", "電網連接與併網量測", "Grid connection",
                   ("WCNV_VtgMsCnvGd1", "WCNV_VtgMsCnvGd2", "WCNV_VtgMsCnvGd3", "WCNV_CnvGnFrq"),
                   ("grid_connection",)),
    InspectionItem("yaw", "偏航系統（煞車液壓）", "Yaw system (brake hydraulics)", ("WYAW_YwBrkHyPrs",),
                   ("yaw_brake_hydraulics",), extra_codes=(223,)),
    InspectionItem("nacelle_ventilation", "機艙通風與溫度", "Nacelle ventilation", ("WNAC_NacTmp", "WNAC_NacCabTmp"),
                   ("nacelle_ventilation",)),
    InspectionItem("generator", "發電機定子", "Generator stator",
                   ("WGEN_GnStaTmp1", "WGEN_GnStaTmp2", "WGEN_GnAirTmp1"), ("generator_stator",)),
    InspectionItem("main_bearing", "主軸承與振動", "Main bearing and vibration",
                   ("WGEN_GnBrgTmp1", "WGEN_GnBrgTmp2", "WNAC_VibMsNacXDir", "WNAC_VibMsNacYDir"),
                   ("main_bearing",)),
    InspectionItem("rotor_speed", "轉速量測", "Rotor speed measurement", ("WROT_RotSpd", "WGEN_GnSpd"),
                   ("rotor_speed_sensor",)),
    InspectionItem("met_sensors", "機艙頂氣象感測器（風速計、風向標）", "Met sensors (anemometer, wind vanes)",
                   ("WMET_WSpeedNac", "WMET_WSpeedRaw", "WYAW_YwVn1AlgnAvg5s", "WYAW_YwVn2AlgnAvg5s"),
                   ("nacelle_anemometer", "wind_vane_1", "wind_vane_alignment")),
    InspectionItem("pitch", "輪轂與變槳系統", "Hub and pitch system",
                   ("WROT_PtAngValBl1", "WROT_PtAngValBl2", "WROT_PtAngValBl3",
                    "WROT_PtMotCurBl1", "WROT_PtMotCurBl2", "WROT_PtMotCurBl3"),
                   ("pitch_control_system", "pitch_system_blade_1")),
    InspectionItem("blades", "葉片（目視）", "Blades (visual)", (), ("blades",)),
)


@lru_cache(maxsize=1)
def code_items() -> Dict[int, str]:
    """事件碼 → 清單項目 ID（由 PLC 的判定規則推出來）。"""
    from server.briefing import CODE_TAGS, _rule_signals, related_tags

    out: Dict[int, str] = {}
    for item in CHECKLIST:
        for code in item.extra_codes:
            out[code] = item.id
    for code in sorted(set(_rule_signals()) | set(CODE_TAGS)):
        if code in out:
            continue
        tags = related_tags(code)
        if not tags:
            continue
        for item in CHECKLIST:
            if tags[0] in item.tags:
                out[code] = item.id
                break
    return out


def item_of_code(code: Optional[int]) -> Optional[str]:
    """一個事件碼屬於清單的哪一項；對不到為 None。"""
    return code_items().get(code) if code is not None else None


def item_of_component(component: Optional[str]) -> Optional[str]:
    """一個部件屬於清單的哪一項（評分用）；對不到為 None。"""
    for item in CHECKLIST:
        if component in item.components:
            return item.id
    return None
