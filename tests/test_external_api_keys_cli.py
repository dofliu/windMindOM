"""``tools/external_api_keys.py``：對外唯讀 API 的金鑰管理 CLI（WMOM-20261125-02）。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _path in (PROJECT_ROOT, PROJECT_ROOT / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import external_api_keys as cli  # noqa: E402
from modules.auth import api_keys as ak  # noqa: E402
from modules.auth.repository import SqlApiKeyStore  # noqa: E402


@pytest.fixture(autouse=True)
def _auth_db(tmp_path, monkeypatch) -> Iterator[Path]:
    db = tmp_path / "auth.db"
    monkeypatch.setenv("WMOM_AUTH_DB_URL", f"sqlite:///{db}")
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)
    ak.set_api_key_store(None)
    yield db
    ak.set_api_key_store(None)


def test_create_prints_the_key_once_and_stores_only_its_hash(_auth_db: Path, capsys) -> None:
    assert cli.main(["create", "rag-assistant"]) == 0
    out, err = capsys.readouterr()
    (key,) = [line for line in out.splitlines() if line.startswith(ak.API_KEY_PREFIX)]
    assert "WMOM_AUTH_ENFORCE" in err, "伺服器沒強制登入時要提醒：金鑰擋不住其他端點"
    # 另一個 store（＝伺服器那個程序）立刻認得這把金鑰；DB 裡找不到金鑰本身
    record = SqlApiKeyStore(f"sqlite:///{_auth_db}").get_by_hash(ak.api_key_digest(key))
    assert record is not None and record.name == "rag-assistant" and record.created_by == cli.CLI_ACTOR
    assert key.encode() not in _auth_db.read_bytes()

    assert cli.main(["list"]) == 0
    listed = capsys.readouterr().out
    assert record.id in listed and record.prefix in listed and key not in listed


def test_no_reminder_when_login_is_enforced(capsys, monkeypatch) -> None:
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert cli.main(["create", "rag"]) == 0
    assert capsys.readouterr().err == ""


def test_revoke_and_errors(_auth_db: Path, capsys) -> None:
    assert cli.main(["list"]) == 0 and "沒有金鑰" in capsys.readouterr().out
    assert cli.main(["create", "rag"]) == 0
    capsys.readouterr()
    (record,) = ak.get_api_key_store().list_keys()
    assert cli.main(["revoke", record.id]) == 0
    assert not SqlApiKeyStore(f"sqlite:///{_auth_db}").list_keys()[0].is_active
    assert cli.main(["list"]) == 0 and "已撤銷" in capsys.readouterr().out
    assert cli.main(["revoke", "no-such-id"]) == 1
    assert cli.main(["create", "   "]) == 2
    with pytest.raises(SystemExit):
        cli.main([])
