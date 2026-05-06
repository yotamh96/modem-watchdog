"""--explain output format: per-modem decision rationale (text).

Claude's Discretion (CONTEXT.md):
  Default format is human-readable text printed to stdout. ``--json`` emits
  the structured form alongside. Both formats are stable across releases.

Used by ``spark-modem diag --explain`` and ``spark-modem recovery --explain``.
"""

from __future__ import annotations

from collections.abc import Iterable

from spark_modem.wire.diag import Diag, PlannedAction


def format_diag_explain(diag: Diag) -> str:
    """One line per modem: state-relevant fields + issue list.

    Output shape::

        Diag cycle=<N> ts=<ISO>
          modem <usb_path> [<cdc_wdm>]: reg=<reg> sim_state=<sim>
            signal=rsrp=<dBm> rsrq=<dB> snr=<dB>
            issues=[(category, detail), ...]
    """
    lines = [f"Diag cycle={diag.cycle_id} ts={diag.ts_iso}"]
    for usb_path, snap in sorted(diag.per_modem.items()):
        issue_pairs = [(i.category.value, i.detail.value) for i in snap.issues]
        line = (
            f"  modem {usb_path} [{snap.cdc_wdm}]: "
            f"reg={snap.registration} sim_state={snap.sim_state} "
            f"signal=rsrp={snap.signal.rsrp_dbm}dBm "
            f"rsrq={snap.signal.rsrq_db}dB "
            f"snr={snap.signal.snr_db}dB "
            f"issues={issue_pairs}"
        )
        lines.append(line)
    return "\n".join(lines)


def format_plans_explain(plans: Iterable[PlannedAction]) -> str:
    """One line per planned action: gates + suppression flags + reason.

    Output shape::

        Plans:
          [RUN|GATED] kind=<kind> who=<usb_path|host> reason=<reason>
            signal_gate=<bool> backoff_gate=<bool> dry_run=<bool>
    """
    lines = ["Plans:"]
    for p in plans:
        who = getattr(p.who, "usb_path", "host")
        gated = (
            p.suppressed_by_backoff
            or p.suppressed_by_signal_gate
            or p.suppressed_by_dry_run
        )
        tag = "GATED" if gated else "RUN"
        lines.append(
            f"  {tag} kind={p.kind.value} who={who} reason={p.reason} "
            f"signal_gate={p.suppressed_by_signal_gate} "
            f"backoff_gate={p.suppressed_by_backoff} "
            f"dry_run={p.suppressed_by_dry_run}"
        )
    return "\n".join(lines)
