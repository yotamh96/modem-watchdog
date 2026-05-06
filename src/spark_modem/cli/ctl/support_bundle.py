"""ctl support-bundle — redacted tarball per C-04 / NFR-22 / NFR-22.1.

Contents (Phase 2):
  - last 200 events from events.jsonl (ICCID/IMSI redacted)
  - all state/by-usb/*.json (ICCID/IMSI redacted)
  - current globals.json
  - current status.json
  - /etc/spark-modem-watchdog/conf.d/* excluding ``hmac-secret``
  - metadata.json with tool version + host + ts + redacted webhook URL

Phase 2 limitation: ``journalctl`` and ``dmesg`` are NOT included
because their capture requires subprocess invocation, which is outside
``src/spark_modem/subproc/`` (SP-04 lint gate). Phase 3 wires them
through ``subproc.run`` once the daemon-mode subprocess surface is
available. The bundle's value (events + state + status + conf) is
sufficient for Phase 2 NOC use.

Redactions are one-way and consistent: same ICCID/IMSI → same
``<redacted:<sha256[:8]>>`` across the bundle for cross-file identity
correlation. HMAC secret is never copied. Webhook URL is host-only.

File mode: 0o640 (root:adm-readable). Operators must ``sudo`` to copy
the bundle off the box; no world-readable artefact.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import socket
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path

from spark_modem.cli.ctl.history import read_events_with_rotated_siblings
from spark_modem.cli.redact import (
    redact_iccid_imsi_in_dict,
    redact_webhook_url_to_host_only,
)
from spark_modem.state_store.store import StateStore

_DEFAULT_OUTPUT_ROOT = Path("/var/lib/spark-modem-watchdog/support-bundles")
_DEFAULT_CONF_D = Path("/etc/spark-modem-watchdog/conf.d")
_DEFAULT_EVENTS_LOG = Path("/var/log/spark-modem-watchdog/events.jsonl")
_LAST_N_EVENTS = 200
_BUNDLE_MODE = 0o640


async def build_support_bundle(
    *,
    out_path: Path | None = None,
    state_root: Path | None = None,
    events_log_path: Path | None = None,
    conf_d_path: Path | None = None,
    webhook_url_for_redaction: str | None = None,
) -> Path:
    """Assemble + redact a tarball; return the path of the bundle.

    All input paths are dependency-injected for tests; production callers
    pass None and the defaults bind to ``/var/lib/...`` / ``/var/log/...``
    / ``/etc/...``.
    """
    store = StateStore(state_root_override=state_root)
    sr = state_root or Path(
        os.environ.get("SPARK_MODEM_STATE_ROOT", "/var/lib/spark-modem-watchdog")
    )
    events_log = events_log_path if events_log_path is not None else _DEFAULT_EVENTS_LOG
    conf_d = conf_d_path if conf_d_path is not None else _DEFAULT_CONF_D

    host = socket.gethostname()
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target_dir = (out_path.parent if out_path else _DEFAULT_OUTPUT_ROOT)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = out_path if out_path is not None else (
        target_dir / f"sparkmd-{host}-{ts}.tar.gz"
    )

    with tarfile.open(target, "w:gz") as tar:
        # Last 200 events (ICCID/IMSI redacted).
        _add_events(tar, events_log)
        # state/by-usb/*.json (ICCID/IMSI redacted).
        _add_state_files(tar, sr)
        # globals.json (no PII; raw).
        await _add_globals(tar, store)
        # status.json (raw).
        _add_status(tar, sr)
        # conf.d/* excluding hmac-secret.
        _add_conf_d(tar, conf_d)
        # metadata.json with redacted webhook URL.
        _add_metadata(tar, webhook_url=webhook_url_for_redaction)

    target.chmod(_BUNDLE_MODE)
    return target


def _add_events(tar: tarfile.TarFile, events_log: Path) -> None:
    events_iter = read_events_with_rotated_siblings(events_log)
    events = list(events_iter)[-_LAST_N_EVENTS:]
    body_parts: list[str] = []
    for ev in events:
        d = ev.model_dump(mode="json")
        d_redacted = redact_iccid_imsi_in_dict(d)
        body_parts.append(json.dumps(d_redacted))
    body = ("\n".join(body_parts) + ("\n" if body_parts else "")).encode("utf-8")
    info = tarfile.TarInfo(name="events.last200.jsonl")
    info.size = len(body)
    info.mode = 0o600
    tar.addfile(info, io.BytesIO(body))


def _add_state_files(tar: tarfile.TarFile, state_root: Path) -> None:
    by_usb = state_root / "state" / "by-usb"
    if not by_usb.is_dir():
        return
    for f in sorted(by_usb.iterdir()):
        if f.suffix == ".json" and ".from-v" not in f.name:
            raw = json.loads(f.read_bytes())
            redacted = redact_iccid_imsi_in_dict(raw)
            body = (json.dumps(redacted, indent=2) + "\n").encode("utf-8")
            info = tarfile.TarInfo(name=f"state/by-usb/{f.name}")
            info.size = len(body)
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(body))


async def _add_globals(tar: tarfile.TarFile, store: StateStore) -> None:
    load = await store.load_globals()
    body = (load.state.model_dump_json(by_alias=True, indent=2) + "\n").encode(
        "utf-8"
    )
    info = tarfile.TarInfo(name="globals.json")
    info.size = len(body)
    info.mode = 0o600
    tar.addfile(info, io.BytesIO(body))


def _add_status(tar: tarfile.TarFile, state_root: Path) -> None:
    path = state_root / "status.json"
    if not path.is_file():
        return
    body = path.read_bytes()
    info = tarfile.TarInfo(name="status.json")
    info.size = len(body)
    info.mode = 0o600
    tar.addfile(info, io.BytesIO(body))


def _add_conf_d(tar: tarfile.TarFile, conf_d: Path) -> None:
    """Add config directory contents, excluding the hmac-secret file."""
    if not conf_d.is_dir():
        return
    for entry in sorted(conf_d.iterdir()):
        if entry.is_file() and entry.name != "hmac-secret":
            body = entry.read_bytes()
            info = tarfile.TarInfo(name=f"conf.d/{entry.name}")
            info.size = len(body)
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(body))


def _add_metadata(tar: tarfile.TarFile, *, webhook_url: str | None) -> None:
    meta: dict[str, object] = {
        "tool_version": "spark-modem-watchdog/2.0.0",
        "host": socket.gethostname(),
        "ts_iso": datetime.now(UTC).isoformat(),
        "webhook_url": (
            redact_webhook_url_to_host_only(webhook_url)
            if webhook_url is not None
            else None
        ),
    }
    body = (json.dumps(meta, indent=2) + "\n").encode("utf-8")
    info = tarfile.TarInfo(name="metadata.json")
    info.size = len(body)
    info.mode = 0o600
    tar.addfile(info, io.BytesIO(body))


async def run(args: argparse.Namespace) -> int:
    out_path = Path(args.out) if args.out else None
    try:
        target = await build_support_bundle(out_path=out_path)
    except OSError as exc:
        print(f"ctl support-bundle: failed: {exc}", file=sys.stderr)
        return 1
    print(str(target.resolve()))
    return 0
