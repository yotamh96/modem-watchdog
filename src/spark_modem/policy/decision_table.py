"""RECOVERY_SPEC §4 issue -> action mapping (cheap actions only in Phase 2).

Destructive actions (modem_reset, usb_reset, driver_reset) are listed for
completeness but are NOT registered in actions/dispatcher.py until Phase 4.
The decision table itself includes them so plan 02-10's replay harness
can classify v1's destructive picks against v2's planned destructive
picks.

NOTE: The current `IssueCategory` enum (wire/enums.py) only includes
config / sim / datapath / registration / qmi -- the five categories the
priority order in RECOVERY_SPEC §5 lists at priorities 1-5.  Higher-
priority numbers (power / enumeration / zao / thermal) have IssueDetail
values but no IssueCategory entries; they are observed by Phase 3
dmesg/udev plumbing and re-classified into one of the existing categories
upstream.  This is consistent with the plan's frontmatter assertion that
the table covers "every RECOVERY_SPEC §4 row" for the categories the
enum currently encodes (see 02-05-SUMMARY.md "Decision table coverage").
"""

from __future__ import annotations

from spark_modem.wire.diag import Issue
from spark_modem.wire.enums import ActionKind, IssueCategory, IssueDetail

# Skip reasons used in PlannedAction.reason when no action is taken.
SKIP_REQUIRES_HUMAN = "skip:requires_human"
SKIP_NO_CARD = "skip:no_card"
SKIP_HARDWARE = "skip:hardware"
SKIP_CARRIER_DENIED = "skip:carrier_denied"
SKIP_EXHAUSTED = "skip:exhausted"


# A row's value is either an ActionKind (something to execute) OR a string
# starting with "skip:" (a non-action with a canonical reason).
_DECISION_TABLE: dict[tuple[IssueCategory, IssueDetail], ActionKind | str] = {
    # config -- priority 1
    (IssueCategory.CONFIG, IssueDetail.APN_EMPTY): ActionKind.SET_APN,
    (IssueCategory.CONFIG, IssueDetail.APN_MISMATCH): ActionKind.SET_APN,
    # sim -- priority 2
    (IssueCategory.SIM, IssueDetail.SIM_POWER_DOWN): ActionKind.SIM_POWER_ON,
    (IssueCategory.SIM, IssueDetail.SIM_APP_UNREADABLE): ActionKind.SOFT_RESET,
    (IssueCategory.SIM, IssueDetail.SIM_APP_PIN_REQUIRED): SKIP_REQUIRES_HUMAN,
    (IssueCategory.SIM, IssueDetail.SIM_APP_PUK_REQUIRED): SKIP_REQUIRES_HUMAN,
    (IssueCategory.SIM, IssueDetail.SIM_APP_DETECTED): ActionKind.SOFT_RESET,
    (IssueCategory.SIM, IssueDetail.SIM_CARD_ABSENT): SKIP_NO_CARD,
    (IssueCategory.SIM, IssueDetail.SIM_CARD_ERROR): SKIP_HARDWARE,
    (IssueCategory.SIM, IssueDetail.SIM_CARD_UNREADABLE): ActionKind.SOFT_RESET,
    # datapath -- priority 3
    (IssueCategory.DATAPATH, IssueDetail.RAW_IP_OFF): ActionKind.FIX_RAW_IP,
    (IssueCategory.DATAPATH, IssueDetail.SESSION_DISCONNECTED): ActionKind.MODEM_RESET,
    # registration -- priority 4
    # The escalation ladder (soft -> modem -> usb -> exhausted) is encoded
    # in engine.run_cycle which selects the rung based on the per-modem
    # counter table; the table here lists the BASE action for the issue.
    (IssueCategory.REGISTRATION, IssueDetail.NOT_REGISTERED_SEARCHING): ActionKind.SOFT_RESET,
    (IssueCategory.REGISTRATION, IssueDetail.NOT_REGISTERED_IDLE): ActionKind.SOFT_RESET,
    (IssueCategory.REGISTRATION, IssueDetail.DENIED): SKIP_CARRIER_DENIED,
    # qmi -- priority 5
    (IssueCategory.QMI, IssueDetail.QMI_CHANNEL_HUNG): ActionKind.USB_RESET,
    (IssueCategory.QMI, IssueDetail.OPERATING_MODE_OFFLINE): ActionKind.MODEM_RESET,
    (IssueCategory.QMI, IssueDetail.OPERATING_MODE_LOW_POWER): ActionKind.MODEM_RESET,
    (IssueCategory.QMI, IssueDetail.QMI_PROXY_DIED): ActionKind.DRIVER_RESET,
    (IssueCategory.QMI, IssueDetail.QMI_TIMEOUT): ActionKind.SOFT_RESET,
    # Plan 04-02 / A-06: Sierra EM7421 stuck-in-bootloader.
    # Per PATTERNS correction #4 the row lives under QMI (not a
    # nonexistent ENUMERATION category). The parent-hub variant
    # (PITFALLS §1.6) is selected via ActionContext.target = "parent-hub"
    # set by the operator-explicit CLI flag (`spark-modem reset --target=parent-hub`)
    # OR by future engine logic that infers the variant from the IssueDetail.
    # The decision-table row routes to USB_RESET; variant selection
    # happens at the action-execution boundary in actions/usb_reset.py.
    (IssueCategory.QMI, IssueDetail.SIERRA_BOOTLOADER): ActionKind.USB_RESET,
}


_PRIORITY_ORDER: tuple[IssueCategory, ...] = (
    IssueCategory.CONFIG,
    IssueCategory.SIM,
    IssueCategory.DATAPATH,
    IssueCategory.REGISTRATION,
    IssueCategory.QMI,
)


def select_top_priority_issue(issues: list[Issue]) -> Issue | None:
    """RECOVERY_SPEC §5: highest-priority category wins.

    First issue in that category is the one this cycle acts on (FR-20:
    at most one action per modem per cycle).
    """
    if not issues:
        return None
    for category in _PRIORITY_ORDER:
        for issue in issues:
            if issue.category == category:
                return issue
    return None


def lookup_action(
    category: IssueCategory, detail: IssueDetail
) -> ActionKind | str | None:
    """Return ActionKind, skip-reason string, or None for unrecognised pairs.

    Unrecognised pairs (e.g. a CONFIG category against a QMI_TIMEOUT detail)
    return None; the caller logs and skips.
    """
    return _DECISION_TABLE.get((category, detail))


def all_table_rows() -> list[tuple[IssueCategory, IssueDetail]]:
    """Public for tests + tools/check_spec.py.

    Returns the (category, detail) keys in deterministic sorted order.
    """
    return sorted(_DECISION_TABLE.keys())
