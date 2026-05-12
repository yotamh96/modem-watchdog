"""L-05 unit tests for `spark-modem ctl config-check`."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from spark_modem.cli.ctl import config_check
from spark_modem.config.settings import Settings

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="owner/mode checks use Linux stat semantics (st_uid, st_gid, chmod 0600)",
    ),
]


@pytest.fixture
def secret_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect Settings.resolve_hmac_secret_path() to a tmp_path file."""
    target = tmp_path / "hmac-secret"

    def _resolve(self: Settings) -> Path:
        return target

    monkeypatch.setattr(Settings, "resolve_hmac_secret_path", _resolve)
    return target


async def test_missing_file_returns_2(
    secret_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # behavior 1: file does not exist
    rc = await config_check.run(argparse.Namespace())
    assert rc == 2
    assert "not found" in capsys.readouterr().err


async def test_placeholder_sentinel_returns_2(
    secret_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # behavior 2: file contains the placeholder sentinel
    secret_path.write_bytes(b"REPLACE_THIS_BEFORE_FIRST_START_SEE_RUNBOOK\n")
    os.chmod(secret_path, 0o600)

    real_stat = os.stat

    def fake_stat(path: str | bytes | os.PathLike[str]) -> os.stat_result:
        st = real_stat(path)
        import types

        return types.SimpleNamespace(  # type: ignore[return-value]
            st_mode=st.st_mode,
            st_uid=0,
            st_gid=0,
            st_size=st.st_size,
        )

    monkeypatch.setattr(config_check.os, "stat", fake_stat)
    rc = await config_check.run(argparse.Namespace())
    assert rc == 2
    assert "placeholder" in capsys.readouterr().err


async def test_empty_file_returns_2(
    secret_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # behavior 3: file is 0 bytes
    secret_path.write_bytes(b"")
    os.chmod(secret_path, 0o600)

    real_stat = os.stat

    def fake_stat(path: str | bytes | os.PathLike[str]) -> os.stat_result:
        st = real_stat(path)
        import types

        return types.SimpleNamespace(  # type: ignore[return-value]
            st_mode=st.st_mode,
            st_uid=0,
            st_gid=0,
            st_size=st.st_size,
        )

    monkeypatch.setattr(config_check.os, "stat", fake_stat)
    rc = await config_check.run(argparse.Namespace())
    assert rc == 2
    assert "empty" in capsys.readouterr().err


async def test_wrong_mode_returns_2(
    secret_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # behavior 4: file has mode 0644 (not 0600)
    secret_path.write_bytes(b"realsecretbytes\n")
    os.chmod(secret_path, 0o644)
    rc = await config_check.run(argparse.Namespace())
    assert rc == 2
    err = capsys.readouterr().err
    assert "mode" in err or "permission" in err


async def test_green_path(
    secret_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # behavior 5: file exists, non-empty, not sentinel, mode 0600, owner root:root (mocked)
    secret_path.write_bytes(b"realsecretbytes_at_least_one_byte\n")
    os.chmod(secret_path, 0o600)

    real_stat = os.stat

    def fake_stat(path: str | bytes | os.PathLike[str]) -> os.stat_result:
        st = real_stat(path)
        import types

        return types.SimpleNamespace(  # type: ignore[return-value]
            st_mode=st.st_mode,
            st_uid=0,
            st_gid=0,
            st_size=st.st_size,
        )

    monkeypatch.setattr(config_check.os, "stat", fake_stat)
    rc = await config_check.run(argparse.Namespace())
    assert rc == 0


async def test_settings_validation_failure_returns_2(
    secret_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # behavior 6: Settings() raises ValidationError (e.g. bad webhook_url)
    monkeypatch.setenv("SPARK_MODEM_WEBHOOK_URL", "ftp://bogus")
    rc = await config_check.run(argparse.Namespace())
    assert rc == 2
    assert "settings invalid" in capsys.readouterr().err
