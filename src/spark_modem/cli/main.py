"""spark-modem CLI entry point — argparse subcommand dispatch.

Wired in pyproject.toml::

    [project.scripts]
    spark-modem = "spark_modem.cli.main:main"

Six top-level subcommands (FR-50): diag / recovery / provision / reset /
status / ctl. ``ctl`` has three sub-subcommands: history / maintenance /
support-bundle. Each subcommand handler is an ``async def run(args) -> int``
returning a Unix exit code; ``main`` runs them via ``asyncio.run``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from spark_modem.cli import diag as diag_cmd
from spark_modem.cli import provision as provision_cmd
from spark_modem.cli import recovery as recovery_cmd
from spark_modem.cli import reset as reset_cmd
from spark_modem.cli import status as status_cmd
from spark_modem.cli.ctl import capture_fleet_fixture as ctl_capture_fleet
from spark_modem.cli.ctl import history as ctl_history
from spark_modem.cli.ctl import maintenance as ctl_maintenance
from spark_modem.cli.ctl import support_bundle as ctl_support_bundle


def _build_parser() -> argparse.ArgumentParser:  # noqa: PLR0915 - argparse subparser wiring is a single block by design
    parser = argparse.ArgumentParser(prog="spark-modem")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # diag
    p_diag = sub.add_parser("diag", help="Run diagnosis (read-only)")
    p_diag.add_argument("--qmi-fixture-dir", type=str, default=None)
    p_diag.add_argument(
        "--inventory-fixture",
        type=str,
        default=None,
        help="Inventory JSON fixture (default: tests/fixtures/inventory/four_modems.json)",
    )
    p_diag.add_argument(
        "--explain",
        action="store_true",
        help="Human-readable per-modem decision rationale",
    )
    p_diag.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )
    p_diag.set_defaults(func=diag_cmd.run)

    # recovery
    p_rec = sub.add_parser("recovery", help="Plan recovery actions for a Diag")
    p_rec.add_argument("--diag-fixture", type=str, default=None)
    p_rec.add_argument("--qmi-fixture-dir", type=str, default=None)
    p_rec.add_argument(
        "--action",
        type=str,
        default=None,
        help="Force a specific action kind (advisory only in Phase 2)",
    )
    p_rec.add_argument("--explain", action="store_true")
    p_rec.add_argument("--json", action="store_true")
    p_rec.add_argument("--dry-run", action="store_true")
    p_rec.set_defaults(func=recovery_cmd.run)

    # provision
    p_prov = sub.add_parser("provision", help="Set APN for one modem (Phase 3)")
    p_prov.add_argument(
        "--device",
        type=str,
        required=True,
        help="cdc-wdmN device basename",
    )
    p_prov.add_argument("--apn", type=str, required=True)
    p_prov.add_argument("--dry-run", action="store_true")
    p_prov.set_defaults(func=provision_cmd.run)

    # reset
    p_res = sub.add_parser("reset", help="Run a single recovery action")
    p_res.add_argument(
        "--action",
        type=str,
        required=True,
        help="Action kind (e.g. soft_reset, set_apn)",
    )
    p_res.add_argument(
        "--modem",
        type=str,
        required=True,
        help="cdc-wdmN device basename",
    )
    p_res.add_argument("--dry-run", action="store_true")
    p_res.add_argument(
        "--target",
        choices=["child-port", "parent-hub"],
        default="child-port",
        help=(
            "usb_reset variant; parent-hub re-fires the boot transition for"
            " Sierra EM7421 stuck-in-bootloader (PITFALLS §1.6 / Plan 04-02 A-06)."
            " Ignored by every other action kind."
        ),
    )
    p_res.set_defaults(func=reset_cmd.run)

    # status
    p_st = sub.add_parser("status", help="Print status.json contents")
    p_st.add_argument(
        "--state-root",
        type=str,
        default=None,
        help="Override state root (default: /var/lib/spark-modem-watchdog)",
    )
    p_st.set_defaults(func=status_cmd.run)

    # ctl
    ctl_parser = sub.add_parser("ctl", help="Operator control commands")
    ctl_sub = ctl_parser.add_subparsers(dest="ctl_cmd", required=True)

    # ctl history
    p_hist = ctl_sub.add_parser("history", help="Per-modem event history")
    p_hist.add_argument(
        "--modem",
        type=str,
        default=None,
        help="usb_path or cdc-wdmN",
    )
    p_hist.add_argument(
        "--since",
        type=str,
        default=None,
        help="Duration (e.g. '1h', '30m', '300s')",
    )
    p_hist.add_argument(
        "--events-log",
        type=str,
        default=None,
        help="Override events.jsonl path (default: /var/log/spark-modem-watchdog/events.jsonl)",
    )
    p_hist.set_defaults(func=ctl_history.run)

    # ctl maintenance on/off/status
    p_maint = ctl_sub.add_parser(
        "maintenance",
        help="Maintenance window control (8h hard cap)",
    )
    p_maint_sub = p_maint.add_subparsers(dest="maint_cmd", required=True)

    p_maint_on = p_maint_sub.add_parser("on", help="Enable maintenance window")
    p_maint_on.add_argument(
        "--duration",
        type=str,
        required=True,
        help="Mandatory; e.g. '2h', '30m'; max 8h",
    )
    p_maint_on.set_defaults(func=ctl_maintenance.run_on)

    p_maint_off = p_maint_sub.add_parser("off", help="Disable maintenance window")
    p_maint_off.set_defaults(func=ctl_maintenance.run_off)

    p_maint_st = p_maint_sub.add_parser("status", help="Show maintenance status")
    p_maint_st.set_defaults(func=ctl_maintenance.run_status)

    # ctl support-bundle
    p_sb = ctl_sub.add_parser(
        "support-bundle",
        help="Build redacted support tarball",
    )
    p_sb.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output path (default: /var/lib/.../support-bundles/...)",
    )
    p_sb.set_defaults(func=ctl_support_bundle.run)

    # ctl capture-fleet-fixture (Phase 5 X-01 / X-02)
    p_cff = ctl_sub.add_parser(
        "capture-fleet-fixture",
        help="Capture per-box (firmware, SDK, libqmi) triple + redacted qmicli fixtures",
    )
    p_cff.add_argument(
        "--out",
        type=str,
        required=True,
        help="Output directory for the per-box fixture tree",
    )
    p_cff.set_defaults(func=ctl_capture_fleet.run)

    return parser


def main(argv: list[str] | None = None) -> int:
    """spark-modem entry point. Returns a Unix exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    rc: int = asyncio.run(args.func(args))
    return rc


if __name__ == "__main__":
    sys.exit(main())
