"""X-03 daemon preflight — refuse to start on unknown fleet triple.

Phase 5 addition (CONTEXT.md X-03 + RESEARCH Q1/Q4). Slots into
``daemon/main.py`` between the existing FR-60 ``preflight_check()`` and
``acquire_pid_lock()``. On unknown-triple failure, raises
``UnknownFleetTriple`` which the caller translates to:

  1. ``write_last_config_error`` marker (same path as ``PreflightFailed``)
  2. ``logger.error`` journalctl line (same shape)
  3. exit code 78 (``EX_CONFIG`` from ``sysexits.h``)

The boot classifier (``lifecycle.classify_prior_run``) reads
``last-config-error`` on the NEXT boot and emits
``DaemonRestart(reason=CONFIG_INVALID)`` — uniform with the FR-60 path.

Index format (RESEARCH Q1 final): per-box subdirectories at
``/etc/spark-modem-watchdog/known-fleet/<box-id>/triple.json``, each
containing JSON with ``em7421_firmware`` / ``zao_sdk`` / ``libqmi`` fields.
dpkg-managed; daemon is read-only.

The daemon writes NOTHING to ``/etc/spark-modem-watchdog/known-fleet/``.
The acceptance-criteria grep (Plan 05-04) pins zero write-path references
to "known-fleet" anywhere in this module — search for ``write_bytes`` /
``write_text`` / ``atomic_write_bytes`` / ``open(... 'w'...)`` should
return zero matches in this file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Final

from spark_modem.inventory.sysfs import SysfsInventory
from spark_modem.qmi.version import (
    FleetTriple,
    QmiVersionDetectionFailed,
    compute_fleet_triple,
)
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.subproc import runner as subproc_runner

logger = logging.getLogger(__name__)

_KNOWN_FLEET_DIR: Final[Path] = Path("/etc/spark-modem-watchdog/known-fleet")
_DEFAULT_ZAO_LOG_PATH: Final[Path] = Path("/var/log/zao-remote-endpoint.log")


class UnknownFleetTriple(RuntimeError):  # noqa: N818 — matches PreflightFailed shape
    """Raised when the local (firmware, SDK, libqmi) triple is not in
    the known-fleet index baked into the .deb (Phase 5 X-03).

    Subclass of ``RuntimeError`` so callers that catch ``RuntimeError``
    only (or its descendants) still see the failure as a runtime problem.
    Does NOT subclass ``PreflightFailed`` (different module, different
    exit-code framing); ``daemon/main.py`` composes them at the call site.
    """


def _load_known_triples(known_fleet_dir: Path) -> list[FleetTriple]:
    """Walk ``known_fleet_dir`` for ``<box-id>/triple.json`` files; load each
    into a ``FleetTriple``. Skip files that fail to parse (warn).

    Returns the list (possibly empty). Does not raise if the directory
    itself is missing — caller handles that case explicitly.

    Walks ONLY one level deep: ``<known-fleet>/<box-id>/triple.json``.
    Nested ``triple.json`` files deeper in the tree are NOT picked up
    (pinned by ``test_nested_triple_json_not_picked_up``).
    """
    if not known_fleet_dir.is_dir():
        return []
    triples: list[FleetTriple] = []
    for box_dir in sorted(known_fleet_dir.iterdir()):
        if not box_dir.is_dir():
            continue
        triple_file = box_dir / "triple.json"
        if not triple_file.is_file():
            continue
        try:
            raw = json.loads(triple_file.read_text(encoding="utf-8"))
            triples.append(
                FleetTriple(
                    em7421_firmware=raw["em7421_firmware"],
                    zao_sdk=raw["zao_sdk"],
                    libqmi=raw["libqmi"],
                )
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning(
                "skipping malformed known-fleet entry at %s: %s",
                triple_file,
                exc,
            )
    return triples


async def _compute_local_triple(*, zao_log_path: Path) -> FleetTriple:
    """Probe the local box for its triple.

    Picks the first modem from ``SysfsInventory`` for the firmware probe.
    All modems on a box share firmware in the homogeneous-fleet assumption
    per CONTEXT.md, so probing the first is sufficient for the triple.
    """
    inventory = SysfsInventory()
    descriptors = await inventory.scan()
    if not descriptors:
        raise UnknownFleetTriple(
            "no Sierra modems found on sysfs; cannot compute fleet triple "
            "(is ModemManager masked and Zao running?)"
        )
    first = descriptors[0]
    wrapper = QmiWrapper(runner=subproc_runner, device=f"/dev/{first.cdc_wdm}")
    try:
        return await compute_fleet_triple(wrapper=wrapper, zao_log_path=zao_log_path)
    except QmiVersionDetectionFailed as exc:
        raise UnknownFleetTriple(
            f"failed to compute local fleet triple: {exc!s}"
        ) from exc


async def preflight_check_known_fleet_triple(
    *,
    known_fleet_dir: Path = _KNOWN_FLEET_DIR,
    zao_log_path: Path = _DEFAULT_ZAO_LOG_PATH,
    local_triple: FleetTriple | None = None,
) -> None:
    """X-03: refuse to start if local triple is not in the known set.

    Args:
        known_fleet_dir: directory of ``<box-id>/triple.json`` files
            (default: ``/etc/spark-modem-watchdog/known-fleet/``).
        zao_log_path: Zao log path for SDK detection.
        local_triple: if provided, skip probing and compare directly
            (test-injection seam; production always passes None).

    Raises:
        UnknownFleetTriple: when the local triple is absent from the
            set, when the local triple cannot be computed, or when the
            known-fleet directory is empty / missing.
    """
    if local_triple is None:
        local = await _compute_local_triple(zao_log_path=zao_log_path)
    else:
        local = local_triple

    known = _load_known_triples(known_fleet_dir)
    if not known:
        raise UnknownFleetTriple(
            f"known-fleet index is empty or missing at {known_fleet_dir} "
            f"(local triple: em7421_firmware={local.em7421_firmware}, "
            f"zao_sdk={local.zao_sdk}, libqmi={local.libqmi}). "
            f"Run 'spark-modem ctl capture-fleet-fixture --out=/tmp/fixture' "
            f"and commit the resulting triple.json to "
            f"tests/fixtures/fleet/<box-id>/ before retrying."
        )

    if local not in known:
        raise UnknownFleetTriple(
            f"unknown fleet triple: em7421_firmware={local.em7421_firmware}, "
            f"zao_sdk={local.zao_sdk}, libqmi={local.libqmi} not in "
            f"{known_fleet_dir} (known set has {len(known)} entries). "
            f"Run 'spark-modem ctl capture-fleet-fixture --out=/tmp/fixture' "
            f"and commit the resulting triple.json to "
            f"tests/fixtures/fleet/<box-id>/ before retrying."
        )
