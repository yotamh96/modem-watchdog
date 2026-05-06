"""CLI helpers — production-grade Inventory / Clock / Zao stubs for laptop CLI mode.

Production code under ``src/spark_modem/`` MUST NEVER import from
``tests/fakes/*``. These types fill that role for laptop CLI mode so the
``cli/`` package stays inside the production import surface.

Surfaces:
  - ``_CliClock``           — real-clock implementation matching ClockProto.
  - ``_InventoryFromFile``  — InventorySource that reads modem descriptors
                               from a JSON fixture file.
  - ``_NoZaoTailer``        — ZaoLogTailer that always reports unknown
                               (no Zao log on a developer laptop).
  - ``FixtureRunner``       — SubprocRunner-shaped fake that loads canned
                               qmicli stdout from
                               ``tests/fixtures/qmicli/<intent>/<libqmi-version>/<scenario>.txt``
                               (or any user-supplied directory with the same shape).
  - ``build_default_settings`` — Settings() bound to ``/tmp/spark-modem-cli``
                               so ``recovery --diag-fixture=`` runs with
                               benign, side-effect-free defaults.
"""

from __future__ import annotations

import json
import time as _time
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from spark_modem.config.settings import Settings
from spark_modem.inventory.descriptor import ModemDescriptor
from spark_modem.qmi.parsers._header import strip_header
from spark_modem.subproc.result import CompletedProcess
from spark_modem.zao_log.snapshot import ZaoSnapshot


class _CliClock:
    """Real-clock implementation matching the Phase 2 ClockProto.

    Mirrors the call surface exposed by ``spark_modem.clock.clock`` module
    functions but as instance methods so a single ``_CliClock`` can be
    parameterized into multiple subsystems (observer, policy.context,
    diag_builder) without monkeypatching the module.
    """

    def monotonic(self) -> float:
        return _time.monotonic()

    def wall_clock_iso(self) -> str:
        return datetime.now(UTC).isoformat()

    def unix_seconds(self) -> int:
        """Unix wall-clock seconds for wire-format replay timestamps.

        Used by webhook/poster for the ``X-Spark-Timestamp`` header
        (FR-44.2 / ADR-0011).  CLAUDE.md invariant #4 requires
        ``time.time()`` (NOT ``time.monotonic()``) for any wall-clock
        stamp that crosses the wire.
        """
        return int(_time.time())


class _InventoryFromFile:
    """InventorySource that reads modem descriptors from a JSON fixture file.

    Intended for ``spark-modem diag --qmi-fixture-dir=...`` on a developer
    laptop. The JSON shape mirrors ``tests/fakes/inventory.FixtureInventory``::

        {"modems": [{"line": 1, "cdc_wdm": "cdc-wdm0", "usb_path": "2-3.1.1", ...}]}
    """

    def __init__(self, fixture_path: Path) -> None:
        self._path = Path(fixture_path)

    async def scan(self) -> list[ModemDescriptor]:
        raw = json.loads(self._path.read_bytes())
        modems = raw.get("modems", [])
        return [ModemDescriptor.model_validate(m) for m in modems]


class _NoZaoTailer:
    """ZaoLogTailer that always reports unknown (no Zao log on a laptop).

    The observer's FR-10 gate consults ``is_line_active(line_idx)`` before
    QMI-probing each line. Returning False here means the observer always
    proceeds with QMI probing; the laptop CLI has no Zao log to consult.
    Every ``snapshot()`` call returns a fresh ``unknown(reason="cli-mode")``.
    """

    def is_line_active(self, line_idx: int) -> bool:
        del line_idx
        return False

    def snapshot(self) -> ZaoSnapshot:
        return ZaoSnapshot.unknown(reason="cli-mode")


def build_default_settings() -> Settings:
    """Build Settings using only env-var defaults; no YAML loaded.

    Paths are bound to ``/tmp/spark-modem-cli`` so ``recovery
    --diag-fixture=...`` runs without touching ``/var/lib/spark-modem-watchdog``
    on a developer laptop.
    """
    return Settings(
        state_root="/tmp/spark-modem-cli",  # noqa: S108 — laptop CLI sandbox path
        run_dir="/tmp/spark-modem-cli/run",  # noqa: S108
        events_log_path="/tmp/spark-modem-cli/events.jsonl",  # noqa: S108
        metrics_socket_path="/tmp/spark-modem-cli/metrics.sock",  # noqa: S108
        carriers_yaml_path="/tmp/spark-modem-cli/carriers.yaml",  # noqa: S108
    )


class FixtureRunner:
    """Reads canned qmicli stdout from disk based on argv intent.

    Resolution::

        argv contains '--nas-get-signal-info' → intent='get_signal'
        → file at <fixture_dir>/get_signal/<libqmi-version>/<scenario>.txt

    Defaults: ``libqmi_version='1.30'``, ``scenario='lte_strong'``.

    If the configured scenario file is absent, the runner falls back to
    *any* ``.txt`` in the version directory so the laptop CLI works
    against the canonical Phase 2 fixture set without further wiring.

    Returns a non-zero ``CompletedProcess`` when no fixture matches the
    intent — callers see this as a typed ``QmiError`` after
    ``QmiWrapper.classify``.
    """

    _INTENT_MAP: ClassVar[dict[str, str]] = {
        "--nas-get-signal-info": "get_signal",
        "--nas-get-serving-system": "get_serving_system",
        "--uim-get-card-status": "get_sim_state",
        "--wds-get-packet-service-status": "get_data_session",
        "--wds-get-current-settings": "get_current_settings",
        "--dms-get-operating-mode": "get_operating_mode",
    }

    def __init__(
        self,
        *,
        fixture_dir: Path,
        libqmi_version: str = "1.30",
        scenario: str = "lte_strong",
    ) -> None:
        self._dir = Path(fixture_dir)
        self._version = libqmi_version
        self._scenario = scenario

    async def run(
        self,
        argv: list[str],
        *,
        timeout_s: float,
        stdin: bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> CompletedProcess:
        del timeout_s, stdin, env  # signature parity only
        intent = self._intent_of(argv)
        if intent is None:
            return CompletedProcess.make(
                argv=argv,
                exit_code=2,
                stdout=b"",
                stderr=b"FixtureRunner: unknown qmicli intent\n",
                duration_monotonic=0.0,
            )
        scenario_path = self._scenario_path(intent)
        if scenario_path is None:
            return CompletedProcess.make(
                argv=argv,
                exit_code=2,
                stdout=b"",
                stderr=f"FixtureRunner: no fixture for intent={intent}\n".encode(),
                duration_monotonic=0.0,
            )
        stdout = strip_header(scenario_path.read_bytes())
        return CompletedProcess.make(
            argv=argv,
            exit_code=0,
            stdout=stdout,
            stderr=b"",
            duration_monotonic=0.001,
        )

    def _intent_of(self, argv: list[str]) -> str | None:
        for elem in argv:
            # Trailing-= flags like --wds-get-profile-settings=3gpp,1
            key = elem.split("=", 1)[0]
            if key in self._INTENT_MAP:
                return self._INTENT_MAP[key]
            if key == "--wds-get-profile-settings":
                return "get_profile_settings"
        return None

    def _scenario_path(self, intent: str) -> Path | None:
        base = self._dir / intent / self._version
        if not base.is_dir():
            return None
        specific = base / f"{self._scenario}.txt"
        if specific.is_file():
            return specific
        # Fall back to any fixture file in the directory so the laptop CLI
        # works against any populated version directory without further wiring.
        for entry in sorted(base.iterdir()):
            if entry.is_file() and entry.suffix == ".txt":
                return entry
        return None
