"""shared/dev_mode.py 單元測試（WMOM-20260510-01 Part A）。

涵蓋：
- ``is_dev_mode_enabled()`` 對各種 env var 值的判定（truthy / falsy / 未設）
- ``log_dev_mode_warning_if_enabled()`` 啟用時 log 警告 + return True；關閉時不 log + return False
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from shared.dev_mode import is_dev_mode_enabled, log_dev_mode_warning_if_enabled


# ─────────────────────────────────────────────────────────────────────────
# is_dev_mode_enabled()
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    ["true", "True", "TRUE", "1", "yes", "Yes", "on", "ON", "  true  "],
)
def test_dev_mode_enabled_for_truthy_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("WMOM_DEV_MODE", value)
    assert is_dev_mode_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "", "anything-else"])
def test_dev_mode_disabled_for_falsy_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("WMOM_DEV_MODE", value)
    assert is_dev_mode_enabled() is False


def test_dev_mode_disabled_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    assert is_dev_mode_enabled() is False


# ─────────────────────────────────────────────────────────────────────────
# log_dev_mode_warning_if_enabled()
# ─────────────────────────────────────────────────────────────────────────


def test_log_warning_when_enabled(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("WMOM_DEV_MODE", "true")
    caplog.set_level(logging.WARNING, logger="shared.dev_mode")
    assert log_dev_mode_warning_if_enabled() is True
    assert any(
        "WMOM_DEV_MODE active" in rec.message and rec.levelno == logging.WARNING
        for rec in caplog.records
    )


def test_no_log_when_disabled(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    caplog.set_level(logging.WARNING, logger="shared.dev_mode")
    assert log_dev_mode_warning_if_enabled() is False
    assert not any(
        "WMOM_DEV_MODE" in rec.message for rec in caplog.records
    )


def test_log_uses_provided_logger(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("WMOM_DEV_MODE", "1")
    custom = logging.getLogger("custom.dev.test")
    caplog.set_level(logging.WARNING, logger="custom.dev.test")
    assert log_dev_mode_warning_if_enabled(custom) is True
    assert any(rec.name == "custom.dev.test" for rec in caplog.records)
