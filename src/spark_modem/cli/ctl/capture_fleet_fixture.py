"""ctl capture-fleet-fixture — Phase 5 X-01 / X-02 fleet-fixture capture.

Operator-invoked once per fleet box during the physical-access window
for Phase 6 prep (CONTEXT.md X-04). Produces a directory tree::

  <out_dir>/
    triple.json                              # FleetTriple JSON shape
    qmi/<usb_path>/<verb>.txt x 7 x N modems # ICCID/IMSI/IP redacted
    zao-log-sample.txt                       # last 50 RASCOW_STAT lines

Runs WITHOUT the daemon (X-03 chicken-and-egg fix per RESEARCH Q2):
capture is a standalone CLI subcommand; it shells out to qmicli via
``subproc.runner.run`` (the same path the daemon's QmiWrapper uses),
but does not participate in the daemon's preflight or PID lock.

PII redaction is one-way and consistent (sha256[:8]); same ICCID/IMSI
appearing across files yields the same ``<redacted:<hash>>`` token so
cross-modem correlation survives without exporting PII.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from spark_modem.cli.redact import redact_pii_from_raw_qmicli
from spark_modem.inventory.descriptor import ModemDescriptor
from spark_modem.inventory.sysfs import SysfsInventory
from spark_modem.qmi.version import FleetTriple, compute_fleet_triple
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.subproc import runner as subproc_runner

# X-02 locked verb list (per CONTEXT.md X-02 §163-170 + RESEARCH Q7).
# Order is intentional: triple-essential verbs first (dms_get_revision),
# SIM identity (uim_get_card_status), then signal/registration/data. The
# tuple shape is deliberate — adding/removing a verb is a deliberate
# change pinned by ``test_qmicli_capture_verbs_list_is_locked_at_7``.
QMICLI_CAPTURE_VERBS: Final[tuple[tuple[str, str], ...]] = (
    ("dms_get_revision", "--dms-get-revision"),
    ("dms_get_operating_mode", "--dms-get-operating-mode"),
    ("uim_get_card_status", "--uim-get-card-status"),
    ("nas_get_signal_info", "--nas-get-signal-info"),
    ("nas_get_serving_system", "--nas-get-serving-system"),
    ("wds_get_current_settings", "--wds-get-current-settings"),
    ("wds_get_profile_settings", "--wds-get-profile-settings"),
)

_DEFAULT_QMICLI_TIMEOUT_S: Final[float] = 8.0
_ZAO_SAMPLE_LINE_COUNT: Final[int] = 50
_DEFAULT_ZAO_LOG_PATH: Final[Path] = Path("/var/log/zao-remote-endpoint.log")
_TRIPLE_SCHEMA_VERSION: Final[int] = 1


def _zao_log_rascow_tail(zao_log_path: Path, line_count: int) -> bytes:
    """Sync helper: read the Zao log and return last N RASCOW_STAT lines.

    Pulled out as a sync function so the async caller can wrap it in
    ``asyncio.to_thread`` (ASYNC240: pathlib I/O should not run on the
    event loop). Returns ``b""`` if the file does not exist.
    """
    try:
        data = zao_log_path.read_bytes()
    except FileNotFoundError:
        return b""
    lines = data.splitlines()
    rascow_lines = [ln for ln in lines if b"RASCOW_STAT" in ln]
    tail = rascow_lines[-line_count:]
    return b"\n".join(tail) + (b"\n" if tail else b"")


async def _capture_zao_log_sample(
    zao_log_path: Path,
    *,
    line_count: int = _ZAO_SAMPLE_LINE_COUNT,
) -> bytes:
    """Return the last ``line_count`` RASCOW_STAT lines from the Zao log.

    Reads the whole file and filters; for the typical Zao log size
    (1-10 MiB), this is acceptable. For larger files a tail-seek would
    be preferable; deferred until soak data shows it matters
    (T-05-03-06 accepted threat).

    Returns ``b""`` if the file does not exist.
    """
    return await asyncio.to_thread(_zao_log_rascow_tail, zao_log_path, line_count)


def _write_modem_verb_output(modem_dir: Path, verb_name: str, body: bytes) -> None:
    """Sync helper: ``mkdir -p`` + write one captured verb output to disk."""
    modem_dir.mkdir(parents=True, exist_ok=True)
    (modem_dir / f"{verb_name}.txt").write_bytes(body)


async def _capture_one_modem(
    descriptor: ModemDescriptor,
    *,
    modem_dir: Path,
) -> None:
    """Run all QMICLI_CAPTURE_VERBS for one modem; write redacted stdout."""
    device = f"/dev/{descriptor.cdc_wdm}"
    for verb_name, verb_arg in QMICLI_CAPTURE_VERBS:
        argv = ["qmicli", "--device-open-proxy", f"--device={device}", verb_arg]
        try:
            cp = await subproc_runner.run(argv, timeout_s=_DEFAULT_QMICLI_TIMEOUT_S)
            redacted = redact_pii_from_raw_qmicli(cp.stdout)
        except Exception as exc:
            # On any failure, write a stub so the operator can see what failed.
            # Broad-except deliberate: operator visibility over strictness for a
            # one-shot capture verb run with physical access to the box.
            redacted = (
                f"# CAPTURE FAILED for {verb_name} on {descriptor.usb_path} "
                f"({descriptor.cdc_wdm}): {type(exc).__name__}: {exc!s}\n"
            ).encode()
        await asyncio.to_thread(_write_modem_verb_output, modem_dir, verb_name, redacted)


def _build_triple_dict(triple: FleetTriple, box_id: str) -> dict[str, object]:
    """Compose the on-disk triple.json payload (sync, no I/O)."""
    return {
        "schema_version": _TRIPLE_SCHEMA_VERSION,
        "em7421_firmware": triple.em7421_firmware,
        "zao_sdk": triple.zao_sdk,
        "libqmi": triple.libqmi,
        "first_seen_box_id": box_id,
        "first_seen_iso": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "_comment": "captured by spark-modem ctl capture-fleet-fixture; "
        "do not hand-edit",
    }


def _write_triple_and_sample(
    out_path: Path,
    triple_payload: dict[str, object],
    sample: bytes,
) -> None:
    """Sync helper: write triple.json + zao-log-sample.txt under ``out_path``."""
    (out_path / "triple.json").write_text(
        json.dumps(triple_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_path / "zao-log-sample.txt").write_bytes(sample)


def _prepare_out_dirs(out_path: Path) -> None:
    """Sync helper: ``mkdir -p`` ``out_path`` and ``out_path/qmi/``."""
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "qmi").mkdir(parents=True, exist_ok=True)


async def build_fleet_fixture(
    *,
    out_path: Path,
    descriptors: list[ModemDescriptor],
    zao_log_path: Path = _DEFAULT_ZAO_LOG_PATH,
    box_id: str = "this-box",
) -> Path:
    """Build the per-box fleet-fixture directory at ``out_path``.

    Args:
        out_path: Target directory; created if absent. Re-runs OVERWRITE
            existing files (atomic per-file, not append-only).
        descriptors: list of ``ModemDescriptor`` (production:
            ``SysfsInventory.scan()``; test: hand-built list).
        zao_log_path: Path to the Zao log for SDK detection + sample.
        box_id: Identifier recorded in ``triple.json``'s ``first_seen_box_id``
            field; defaults to ``"this-box"``.

    Returns:
        ``out_path`` (the directory containing ``triple.json``, ``qmi/``,
        and ``zao-log-sample.txt``).
    """
    await asyncio.to_thread(_prepare_out_dirs, out_path)

    # 1. Per-modem qmicli captures (ADR-0009 usb_path keying).
    for descriptor in descriptors:
        # NOTE: keyed by descriptor.usb_path, NOT descriptor.cdc_wdm.
        # cdc-wdmN renumbers across reboots; usb_path is the canonical
        # identity (ADR-0009).
        modem_dir = out_path / "qmi" / descriptor.usb_path
        await _capture_one_modem(descriptor, modem_dir=modem_dir)

    # 2. Triple (firmware via first modem; sdk via Zao log; libqmi global).
    # Use the FIRST descriptor for the firmware probe — all modems in a single
    # box have the same firmware (homogeneous fleet assumption per CONTEXT.md).
    first = descriptors[0]
    wrapper = QmiWrapper(runner=subproc_runner, device=f"/dev/{first.cdc_wdm}")
    triple = await compute_fleet_triple(wrapper=wrapper, zao_log_path=zao_log_path)

    triple_payload = _build_triple_dict(triple, box_id=box_id)

    # 3. Zao log sample.
    sample = await _capture_zao_log_sample(zao_log_path)

    await asyncio.to_thread(_write_triple_and_sample, out_path, triple_payload, sample)

    return out_path


async def run(args: argparse.Namespace) -> int:
    """argparse dispatcher entry point.

    Production inventory discovery via sysfs (no daemon required, X-03
    chicken-and-egg fix). On a dev laptop without modems present this
    returns an empty list and exits non-zero with a helpful message;
    operators run this on a Jetson box, not a laptop.
    """
    out_path = Path(args.out)
    inventory = SysfsInventory()
    descriptors = await inventory.scan()
    if not descriptors:
        print(
            "capture-fleet-fixture: no Sierra modems found on sysfs; "
            "is ModemManager masked and Zao running?",
            file=sys.stderr,
        )
        return 1
    try:
        target = await build_fleet_fixture(
            out_path=out_path,
            descriptors=descriptors,
        )
    except Exception as exc:
        # Broad-except deliberate: this is the operator-facing error surface;
        # any uncaught exception (QmiVersionDetectionFailed, OSError on
        # write, etc.) should surface as a one-line message + exit 1.
        print(f"capture-fleet-fixture failed: {exc!s}", file=sys.stderr)
        return 1
    print(str(await asyncio.to_thread(target.resolve)))
    return 0
