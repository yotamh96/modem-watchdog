"""Tests for spark_modem.cli.ctl.support_bundle — redacted tarball builder."""

from __future__ import annotations

import json
import re
import sys
import tarfile
from pathlib import Path

import pytest

from spark_modem.cli.ctl.support_bundle import build_support_bundle

_SKIP_WIN = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only chmod 0o640 (Windows ignores POSIX modes)",
)

_REDACTED_RE = re.compile(r"^<redacted:[0-9a-f]{8}>$")


def _make_state_root(tmp_path: Path) -> Path:
    state_root = tmp_path / "state-root"
    (state_root / "state" / "by-usb").mkdir(parents=True, exist_ok=True)
    return state_root


async def test_bundle_creates_tarball_at_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path / "fake-runtime"))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path / "fake-run"))
    state_root = _make_state_root(tmp_path)

    out = tmp_path / "out" / "test.tar.gz"
    result = await build_support_bundle(
        out_path=out,
        state_root=state_root,
        events_log_path=tmp_path / "events.jsonl",
        conf_d_path=tmp_path / "conf.d",
    )
    assert result == out
    assert out.is_file()
    # tarfile.open round-trips the bundle.
    with tarfile.open(out, "r:gz") as tar:
        names = tar.getnames()
    assert "globals.json" in names
    assert "metadata.json" in names


async def test_bundle_redacts_iccid_imsi(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-populated state file with an ICCID is redacted in the bundle."""
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path / "fake-runtime"))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path / "fake-run"))
    state_root = _make_state_root(tmp_path)
    state_file = state_root / "state" / "by-usb" / "2-3.1.1.json"
    state_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "healthy",
                "present": True,
                "rf_blocked": False,
                "iccid": "8997201700123456789",
                "imsi": "425010123456789",
            }
        ),
        encoding="utf-8",
    )

    out = tmp_path / "out" / "redact.tar.gz"
    await build_support_bundle(
        out_path=out,
        state_root=state_root,
        events_log_path=tmp_path / "events.jsonl",
        conf_d_path=tmp_path / "conf.d",
    )
    with tarfile.open(out, "r:gz") as tar:
        member = tar.getmember("state/by-usb/2-3.1.1.json")
        f = tar.extractfile(member)
        assert f is not None
        content = json.loads(f.read())

    assert _REDACTED_RE.match(content["iccid"])
    assert _REDACTED_RE.match(content["imsi"])
    # Non-PII fields untouched.
    assert content["state"] == "healthy"
    assert content["present"] is True


async def test_bundle_excludes_hmac_secret_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Files named 'hmac-secret' under conf.d/ are NEVER copied into the bundle."""
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path / "fake-runtime"))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path / "fake-run"))
    state_root = _make_state_root(tmp_path)
    conf_d = tmp_path / "conf.d"
    conf_d.mkdir(parents=True, exist_ok=True)
    (conf_d / "00-carriers.yaml").write_text("carriers: []\n", encoding="utf-8")
    (conf_d / "hmac-secret").write_bytes(b"super-secret-key-bytes")
    (conf_d / "10-options.yaml").write_text("opt: 1\n", encoding="utf-8")

    out = tmp_path / "out" / "no-hmac.tar.gz"
    await build_support_bundle(
        out_path=out,
        state_root=state_root,
        events_log_path=tmp_path / "events.jsonl",
        conf_d_path=conf_d,
    )
    with tarfile.open(out, "r:gz") as tar:
        names = tar.getnames()
    assert "conf.d/hmac-secret" not in names
    assert "conf.d/00-carriers.yaml" in names
    assert "conf.d/10-options.yaml" in names


@_SKIP_WIN
async def test_bundle_chmod_640(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The output tarball is chmod 0o640 (root:adm-readable; not world-readable)."""
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path / "fake-runtime"))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path / "fake-run"))
    state_root = _make_state_root(tmp_path)
    out = tmp_path / "out" / "perms.tar.gz"
    await build_support_bundle(
        out_path=out,
        state_root=state_root,
        events_log_path=tmp_path / "events.jsonl",
        conf_d_path=tmp_path / "conf.d",
    )
    mode = out.stat().st_mode & 0o777
    assert mode == 0o640


async def test_bundle_metadata_redacts_webhook_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """metadata.json carries only `<scheme>://<host>/` for webhook_url."""
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path / "fake-runtime"))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path / "fake-run"))
    state_root = _make_state_root(tmp_path)
    out = tmp_path / "out" / "meta.tar.gz"
    await build_support_bundle(
        out_path=out,
        state_root=state_root,
        events_log_path=tmp_path / "events.jsonl",
        conf_d_path=tmp_path / "conf.d",
        webhook_url_for_redaction="https://noc.example.com/secret/path?q=1",
    )
    with tarfile.open(out, "r:gz") as tar:
        f = tar.extractfile(tar.getmember("metadata.json"))
        assert f is not None
        meta = json.loads(f.read())
    assert meta["webhook_url"] == "https://noc.example.com/"


async def test_bundle_metadata_webhook_url_none_when_unspecified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path / "fake-runtime"))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path / "fake-run"))
    state_root = _make_state_root(tmp_path)
    out = tmp_path / "out" / "meta-none.tar.gz"
    await build_support_bundle(
        out_path=out,
        state_root=state_root,
        events_log_path=tmp_path / "events.jsonl",
        conf_d_path=tmp_path / "conf.d",
    )
    with tarfile.open(out, "r:gz") as tar:
        f = tar.extractfile(tar.getmember("metadata.json"))
        assert f is not None
        meta = json.loads(f.read())
    assert meta["webhook_url"] is None


async def test_bundle_includes_status_json_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path / "fake-runtime"))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path / "fake-run"))
    state_root = _make_state_root(tmp_path)
    (state_root / "status.json").write_bytes(b'{"some": "report"}')

    out = tmp_path / "out" / "status.tar.gz"
    await build_support_bundle(
        out_path=out,
        state_root=state_root,
        events_log_path=tmp_path / "events.jsonl",
        conf_d_path=tmp_path / "conf.d",
    )
    with tarfile.open(out, "r:gz") as tar:
        names = tar.getnames()
    assert "status.json" in names
