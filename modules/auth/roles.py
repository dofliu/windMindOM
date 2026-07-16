"""RBAC 角色定義（DEC-20260716-01）。

windMindOM 的授權角色，刻意對映 workflow 既有的簽核角色語意（別重造）：

| Role       | signoff group | 語意                         |
|------------|---------------|------------------------------|
| EMPLOYEE   | 100           | 現場工程師 / 派工簽收 / 完工申報 |
| LEADER     | 300           | 組長                          |
| SUPERVISOR | 500           | 主管                          |
| TREASURY   | 666           | 總務 / 庫管                    |
| ADMIN      | 999           | 系統管理員（非簽核角色，全權）  |

本模組**不** import ``modules.workflow``（保持 auth 為更底層、無循環依賴）；
上表的 group 對映由 ``modules.workflow.domain.signoff.user_group_to_level`` 持有，
兩邊的 value 字串刻意一致（employee/leader/supervisor/treasury）以便對照。
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    """使用者的 RBAC 角色。value 與 signoff 角色字串對齊（admin 除外）。"""

    EMPLOYEE = "employee"
    LEADER = "leader"
    SUPERVISOR = "supervisor"
    TREASURY = "treasury"
    ADMIN = "admin"


# signoff user group code → Role（對映 workflow signoff 的 _GROUP_TO_LEVEL + 999 admin）。
_GROUP_TO_ROLE: dict[int, Role] = {
    100: Role.EMPLOYEE,
    300: Role.LEADER,
    500: Role.SUPERVISOR,
    666: Role.TREASURY,
    999: Role.ADMIN,
}


def group_to_role(group: int) -> Role | None:
    """etech user group code（100/300/500/666/999）→ :class:`Role`。

    Args:
        group: etech 沿用的 user group 數字碼。

    Returns:
        對應的 :class:`Role`；未知 group 回 ``None``。
    """
    return _GROUP_TO_ROLE.get(group)
