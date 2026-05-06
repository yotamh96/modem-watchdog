"""Closed enums for the wire boundary.

Every enum is a StrEnum so JSON serialization is automatic and mypy
treats variants as Literals (CLAUDE.md: match — not if/elif — on
ModemState requires Literal-typed values).
"""

from __future__ import annotations

from enum import StrEnum


class IssueCategory(StrEnum):
    """Action priority order: config > sim > datapath > registration > qmi (FR-21)."""

    CONFIG = "config"
    SIM = "sim"
    DATAPATH = "datapath"
    REGISTRATION = "registration"
    QMI = "qmi"


class IssueDetail(StrEnum):
    """Specific diagnosable issues. See docs/RECOVERY_SPEC.md §4 decision table."""

    # Config
    APN_MISMATCH = "apn_mismatch"
    APN_EMPTY = "apn_empty"
    # SIM
    NO_SIM = "no_sim"
    SIM_LOCKED = "sim_locked"
    SIM_APP_DETECTED = "sim_app_detected"
    SIM_CARD_ABSENT = "sim_card_absent"
    SIM_CARD_ERROR = "sim_card_error"
    SIM_CARD_UNREADABLE = "sim_card_unreadable"
    SIM_POWER_DOWN = "sim_power_down"
    SIM_APP_PIN_REQUIRED = "sim_app_pin_required"
    SIM_APP_PUK_REQUIRED = "sim_app_puk_required"
    SIM_APP_UNREADABLE = "sim_app_unreadable"
    # Datapath
    RAW_IP_OFF = "raw_ip_off"
    NO_DATA_SESSION = "no_data_session"
    NO_IPV4 = "no_ipv4"
    SESSION_DISCONNECTED = "session_disconnected"
    # Registration
    NOT_REGISTERED_SEARCHING = "not_registered_searching"
    NOT_REGISTERED_IDLE = "not_registered_idle"
    NOT_REGISTERED_DENIED = "not_registered_denied"
    DENIED = "denied"
    # QMI
    QMI_TIMEOUT = "qmi_timeout"
    QMI_HUNG = "qmi_hung"
    QMI_CHANNEL_HUNG = "qmi_channel_hung"
    QMI_PROXY_DIED = "qmi_proxy_died"
    OPERATING_MODE_OFFLINE = "operating_mode_offline"
    OPERATING_MODE_LOW_POWER = "operating_mode_low_power"
    # Enumeration / power
    ENUMERATION_MISSING = "enumeration_missing"
    ENUMERATION_ADDRESS_FAIL = "enumeration_address_fail"
    ENUMERATION_OVERCURRENT = "enumeration_overcurrent"
    AUTOSUSPEND_ON = "autosuspend_on"
    # Thermal / Zao
    THERMAL_WARN = "thermal_warn"
    THERMAL_CRITICAL = "thermal_critical"
    ZAO_UNIT_INACTIVE = "zao_unit_inactive"
    ZAO_LOG_STALE = "zao_log_stale"


class RegistrationState(StrEnum):
    """LTE registration state from QMI NAS response."""

    REGISTERED_HOME = "registered_home"
    REGISTERED_ROAMING = "registered_roaming"
    NOT_REGISTERED_SEARCHING = "not_registered_searching"
    NOT_REGISTERED_IDLE = "not_registered_idle"
    NOT_REGISTERED_DENIED = "not_registered_denied"
    UNKNOWN = "unknown"


class ActionKind(StrEnum):
    """RECOVERY_SPEC.md ladder: set_apn / fix_raw_ip / sim_power_on /
    soft_reset / set_operating_mode / fix_autosuspend -> modem_reset ->
    usb_reset; global driver_reset.

    Phase 2 cheap actions (registered in actions/dispatcher._REGISTRY):
      SET_APN, FIX_RAW_IP, SIM_POWER_ON, SOFT_RESET, SET_OPERATING_MODE,
      FIX_AUTOSUSPEND.
    Phase 4 destructive actions (NOT registered until Phase 4 + signal-
    quality gate):
      MODEM_RESET, USB_RESET, DRIVER_RESET.
    """

    SET_APN = "set_apn"
    FIX_RAW_IP = "fix_raw_ip"
    SIM_POWER_ON = "sim_power_on"
    SOFT_RESET = "soft_reset"
    SET_OPERATING_MODE = "set_operating_mode"
    FIX_AUTOSUSPEND = "fix_autosuspend"
    MODEM_RESET = "modem_reset"
    USB_RESET = "usb_reset"
    DRIVER_RESET = "driver_reset"


class ActionResult(StrEnum):
    """Outcome codes for an attempted recovery action."""

    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED_SIGNAL_GATE = "skipped_signal_gate"
    SKIPPED_BACKOFF = "skipped_backoff"
    SKIPPED_DRY_RUN = "skipped_dry_run"


class EventKind(StrEnum):
    """events.jsonl variants. discriminator='kind' on the union."""

    ACTION_PLANNED = "action_planned"
    ACTION_EXECUTED = "action_executed"
    ACTION_FAILED = "action_failed"
    STATE_TRANSITION = "state_transition"
    DAEMON_STARTED = "daemon_started"
    DAEMON_STOPPED = "daemon_stopped"
    SCHEMA_DOWNGRADE_PENDING = "schema_downgrade_pending"
    USB_PATH_MISMATCH = "usb_path_mismatch"
    MAINTENANCE_WINDOW_STARTED = "maintenance_window_started"
    MAINTENANCE_WINDOW_ENDED = "maintenance_window_ended"


class WebhookEventKind(StrEnum):
    """webhook payload variants. discriminator='kind' on the union."""

    HEALTHY_TO_DEGRADED = "healthy_to_degraded"
    RECOVERING_TO_EXHAUSTED = "recovering_to_exhausted"
    DAEMON_RESTART = "daemon_restart"
    ACTION_FAILED = "action_failed"


class DowngradeReason(StrEnum):
    """Reason codes for a schema-downgrade event."""

    FILE_TOO_OLD = "file_too_old"
    SCHEMA_MISMATCH = "schema_mismatch"


class DaemonStopReason(StrEnum):
    """Reason enum on daemon_stopped events / DaemonRestart webhooks (M-6)."""

    SIGTERM = "sigterm"
    CRASH = "crash"
    CONFIG_INVALID = "config_invalid"
    OOM = "oom"
    KILL = "kill"
