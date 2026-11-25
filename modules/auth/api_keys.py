"""外部系統的 API 金鑰（WMOM-20261125-02，DEC-20261125-01）。

外部系統（例：RAG 運維助理）不是人員，不走帳密登入與 JWT：發一把長效金鑰，只能用在對外唯讀端點
（``/api/ext/v1``）。

- **金鑰不是角色**：金鑰放在 ``X-API-Key`` header，``get_current_actor`` / ``require_role`` /
  ``require_authenticated`` 都不看它，所以帶金鑰的請求在強制登入的伺服器上碰不到故障注入、答案卷、
  控制與設定等端點。
- **驗證一律強制**：不受 ``WMOM_AUTH_ENFORCE`` 與 dev_mode 影響（沒有 fallback 身分）。
- **儲存**：金鑰格式 ``wmk_<隨機>``，只在建立時回傳一次；儲存端只留 sha256 與前幾碼（供辨識）。
- **store**：預設 ``SqlApiKeyStore``（與使用者同一個 auth DB，``WMOM_AUTH_DB_URL``）。dev_mode 也用它——
  金鑰不是 demo 資料，伺服器重啟後外部系統手上的金鑰要還能用。測試以 ``set_api_key_store`` 注入
  ``InMemoryApiKeyStore``。
"""

from __future__ import annotations

import hashlib
import os
import secrets
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Protocol
from uuid import uuid4

from fastapi import HTTPException, Request, status

API_KEY_PREFIX = "wmk_"
API_KEY_HEADER = "X-API-Key"
# 目前唯一的權限範圍：對外唯讀端點（/api/ext/v1）
SCOPE_EXTERNAL_READ = "external:read"
KNOWN_SCOPES = frozenset({SCOPE_EXTERNAL_READ})
# 顯示用前綴的長度（含 ``wmk_``）；只夠辨識是哪一把，不足以猜出金鑰
_DISPLAY_PREFIX_LEN = len(API_KEY_PREFIX) + 6
# ``last_used_at`` 最多多久寫一次（秒）：避免每個請求都寫 DB
_TOUCH_INTERVAL_S = 60.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ApiKey:
    """一把 API 金鑰的紀錄（不含金鑰本身）。

    Attributes:
        id: 金鑰 ID（管理端點用它撤銷）。
        name: 用途說明（例：``rag-assistant``）。
        prefix: 金鑰的前幾碼（辨識用）。
        key_hash: 金鑰的 sha256（16 進位）。
        scope: 權限範圍。
        created_at: 建立時間（UTC ISO）。
        created_by: 建立者的 actor id。
        last_used_at: 最近一次使用的時間；沒用過為 None。
        revoked_at: 撤銷時間；未撤銷為 None。
    """

    id: str
    name: str
    prefix: str
    key_hash: str
    scope: str
    created_at: str
    created_by: str
    last_used_at: str | None = None
    revoked_at: str | None = None

    @property
    def is_active(self) -> bool:
        """是否仍可使用（未撤銷）。"""
        return self.revoked_at is None


@dataclass(frozen=True)
class ExternalClient:
    """已驗證的外部系統（對外端點的呼叫者）。"""

    key_id: str
    name: str
    scope: str


class ApiKeyStore(Protocol):
    """API 金鑰 store 介面。``InMemoryApiKeyStore``（測試）與 ``SqlApiKeyStore``（預設）皆滿足。"""

    def add(self, key: ApiKey) -> None: ...
    def get_by_hash(self, key_hash: str) -> ApiKey | None: ...
    def list_keys(self) -> list[ApiKey]: ...
    def revoke(self, key_id: str, revoked_at: str) -> bool: ...
    def touch(self, key_id: str, used_at: str) -> None: ...


class InMemoryApiKeyStore:
    """記憶體 API 金鑰 store（測試用）。"""

    def __init__(self) -> None:
        self._by_id: dict[str, ApiKey] = {}

    def add(self, key: ApiKey) -> None:
        """加入一把金鑰。"""
        self._by_id[key.id] = key

    def get_by_hash(self, key_hash: str) -> ApiKey | None:
        """依 sha256 取金鑰；無則 ``None``。"""
        for key in self._by_id.values():
            if key.key_hash == key_hash:
                return key
        return None

    def list_keys(self) -> list[ApiKey]:
        """列出全部金鑰（依建立時間）。"""
        return sorted(self._by_id.values(), key=lambda k: (k.created_at, k.id))

    def revoke(self, key_id: str, revoked_at: str) -> bool:
        """撤銷金鑰；不存在回 False，已撤銷的維持原撤銷時間並回 True。"""
        key = self._by_id.get(key_id)
        if key is None:
            return False
        if key.revoked_at is None:
            self._by_id[key_id] = replace(key, revoked_at=revoked_at)
        return True

    def touch(self, key_id: str, used_at: str) -> None:
        """記下最近一次使用的時間。"""
        key = self._by_id.get(key_id)
        if key is not None:
            self._by_id[key_id] = replace(key, last_used_at=used_at)


def new_api_key() -> str:
    """產生一把金鑰（只回給建立者一次）。

    Returns:
        ``wmk_`` 開頭的隨機字串。
    """
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def api_key_digest(key: str) -> str:
    """金鑰的 sha256（查詢與儲存用）。

    Args:
        key: 金鑰。

    Returns:
        16 進位字串。
    """
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def issue_api_key(store: ApiKeyStore, name: str, created_by: str,
                  scope: str = SCOPE_EXTERNAL_READ) -> tuple[ApiKey, str]:
    """建立並存下一把金鑰。

    Args:
        store: 金鑰 store。
        name: 用途說明。
        created_by: 建立者的 actor id。
        scope: 權限範圍。

    Returns:
        ``(紀錄, 金鑰)``；金鑰只有這一次拿得到。

    Raises:
        ValueError: 不認得的權限範圍，或用途說明是空的。
    """
    if scope not in KNOWN_SCOPES:
        raise ValueError(f"不認得的權限範圍：{scope}")
    name = name.strip()
    if not name:
        raise ValueError("用途說明不能是空的")
    key = new_api_key()
    record = ApiKey(
        id=str(uuid4()),
        name=name,
        prefix=key[:_DISPLAY_PREFIX_LEN],
        key_hash=api_key_digest(key),
        scope=scope,
        created_at=_now_iso(),
        created_by=created_by,
    )
    store.add(record)
    return record, key


# ── 模組層 store（lazy 建立，避免 import 時就碰 DB）──────────────────────────
_store: ApiKeyStore | None = None
_store_lock = threading.Lock()
# key_id → 上次寫 last_used_at 的時間（time.monotonic）
_last_touch: dict[str, float] = {}


def build_default_api_key_store() -> ApiKeyStore:
    """建預設 store：``SqlApiKeyStore``（``WMOM_AUTH_DB_URL``，預設 ``sqlite:///./wmom_auth.db``）。"""
    from .repository import SqlApiKeyStore  # lazy import：避免 api_keys ↔ repository 循環

    db_url = os.environ.get("WMOM_AUTH_DB_URL", "").strip() or "sqlite:///./wmom_auth.db"
    return SqlApiKeyStore(db_url)


def get_api_key_store() -> ApiKeyStore:
    """取得（或首次建立）金鑰 store。"""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = build_default_api_key_store()
    return _store


def set_api_key_store(store: ApiKeyStore | None) -> None:
    """覆寫模組層金鑰 store（測試 / 注入用）；``None`` 表示下次使用時重建預設 store。"""
    global _store
    with _store_lock:
        _store = store
        _last_touch.clear()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "ApiKey"},
    )


def require_api_key(scope: str = SCOPE_EXTERNAL_READ) -> Callable[[Request], ExternalClient]:
    """產生一個 dependency：請求須帶有效、未撤銷、範圍相符的 API 金鑰（``X-API-Key``）。

    一律強制，不看 ``WMOM_AUTH_ENFORCE`` 與 dev_mode。

    Args:
        scope: 端點需要的權限範圍。

    Returns:
        可放進 ``Depends(...)`` 的 dependency callable；通過時回 :class:`ExternalClient`。
    """

    def _dependency(request: Request) -> ExternalClient:
        key = request.headers.get(API_KEY_HEADER, "").strip()
        if not key:
            raise _unauthorized(f"需要 API 金鑰（缺 {API_KEY_HEADER} header）")
        if not key.startswith(API_KEY_PREFIX):
            raise _unauthorized("API 金鑰無效")
        store = get_api_key_store()
        record = store.get_by_hash(api_key_digest(key))
        if record is None or not record.is_active:
            raise _unauthorized("API 金鑰無效或已撤銷")
        if record.scope != scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="這把 API 金鑰沒有此端點的權限",
            )
        now = time.monotonic()
        last = _last_touch.get(record.id)
        if last is None or now - last >= _TOUCH_INTERVAL_S:
            _last_touch[record.id] = now
            store.touch(record.id, _now_iso())
        return ExternalClient(key_id=record.id, name=record.name, scope=record.scope)

    return _dependency
