"""windMindOM auth module — JWT + RBAC 授權層（DEC-20260716-01）。

非破壞式接入：提供 ``get_current_actor`` / ``require_roles`` dependency + ``/api/auth``
router，既有 router 未採用前行為零改變。詳見各子模組 docstring 與
``docs/product/decision_log.md`` DEC-20260716-01。
"""

from .dependencies import Actor, get_current_actor, require_roles
from .roles import Role, group_to_role

__all__ = ["Actor", "Role", "get_current_actor", "group_to_role", "require_roles"]
