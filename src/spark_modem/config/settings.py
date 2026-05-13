"""Settings — env + flag layer (pydantic v2 BaseSettings).

Layered precedence (FR-54): CLI flags > env vars > YAML conf.d/*.yaml > defaults.

This module owns the env+flag layer. The YAML layer is read separately by
yaml_merge.load_yaml_layer and overlaid via Settings.from_yaml_layer; the CLI
flag layer lands in Phase 2 (the `spark-modem` argparse front-end calls
Settings(**cli_overrides)).

Fields are annotated with reload markers (RELOAD_DATA / RELOAD_RESTART) so
Phase 3 SIGHUP can decide what to apply mid-flight.

Imports `BaseSettings` from `pydantic_settings` — the `pydantic-settings>=2.5,<3`
dependency is pinned in `packaging/requirements.in` by Plan 01 (wave 1) and is
available in the dev venv by the time this plan executes (wave 3).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from spark_modem.config.reload_marker import RELOAD_DATA, RELOAD_RESTART


class Settings(BaseSettings):
    """Daemon-wide configuration. Read from env vars; overlay-able with YAML."""

    model_config = SettingsConfigDict(
        env_prefix="SPARK_MODEM_",
        env_nested_delimiter="__",
        extra="forbid",  # Reject unknown SPARK_MODEM_* env vars.
        frozen=True,  # Once loaded, immutable; SIGHUP constructs a new instance.
    )

    # --- Topology fields (RELOAD_RESTART) ---

    state_root: str = Field(
        default="/var/lib/spark-modem-watchdog",
        json_schema_extra=RELOAD_RESTART,
        description="Root dir for persistent state (per-modem files, identity, globals).",
    )
    run_dir: str = Field(
        default="/run/spark-modem-watchdog",
        json_schema_extra=RELOAD_RESTART,
        description="Runtime dir (locks, metrics socket).",
    )
    events_log_path: str = Field(
        default="/var/log/spark-modem-watchdog/events.jsonl",
        json_schema_extra=RELOAD_RESTART,
    )
    metrics_socket_path: str = Field(
        default="/run/spark-modem-watchdog/metrics.sock",
        json_schema_extra=RELOAD_RESTART,
    )
    carriers_yaml_path: str = Field(
        default="/etc/spark-modem-watchdog/conf.d/00-carriers.yaml",
        json_schema_extra=RELOAD_DATA,  # Carrier-table edit is hot-reloadable.
    )
    startup_delay_seconds: int = Field(
        default=15,
        ge=0,
        json_schema_extra=RELOAD_RESTART,
        description="NFR-13 first-cycle exemption window.",
    )

    # --- Recovery / backoff (RELOAD_DATA) ---

    backoff_seconds: int = Field(
        default=300,
        ge=1,
        json_schema_extra=RELOAD_DATA,
        description="FR-25 same-action backoff (default 300s).",
    )
    ladder_min_interval_seconds: int = Field(
        default=90,
        ge=1,
        json_schema_extra=RELOAD_DATA,
        description="FR-25.1 cross-action ladder backoff (default 90s).",
    )
    cycle_interval_seconds: float = Field(
        default=60.0,
        ge=1.0,
        json_schema_extra=RELOAD_DATA,
        description="C-01/C-02: production cycle cadence in seconds; SIGHUP can retune live.",
    )
    healthy_streak_decay_k: int = Field(
        default=10,
        ge=1,
        json_schema_extra=RELOAD_DATA,
        description="ADR-0006 K consecutive Healthy cycles before counters decay.",
    )

    # --- Phase 4 destructive actions: driver_reset eligibility (RELOAD_DATA) ---
    #
    # See .planning/phases/04-destructive-actions-hil/04-CONTEXT.md C-01..C-05.
    # `expected_modem_count` is RELOAD_DATA (not RELOAD_RESTART): the cycle
    # driver re-reads it per cycle to populate PolicyContext.expected_modem_count,
    # so a SIGHUP edit is naturally consumed at the next cycle boundary without
    # needing a daemon restart.
    multi_modem_threshold_fraction: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        json_schema_extra=RELOAD_DATA,
        description="FR-24 driver_reset eligibility fraction (default 0.75; per C-01).",
    )
    expected_modem_count: int = Field(
        default=4,
        ge=1,
        le=99,
        json_schema_extra=RELOAD_DATA,
        description="FR-24 driver_reset denominator (total fleet size; per C-01).",
    )
    global_driver_reset_backoff_seconds: int = Field(
        default=3600,
        ge=1,
        json_schema_extra=RELOAD_DATA,
        description="RECOVERY_SPEC §6.4 driver_reset cooldown (default 3600s; per C-05).",
    )
    modprobe_timeout_seconds: int = Field(
        default=30,
        ge=1,
        json_schema_extra=RELOAD_DATA,
        description="A-03 driver_reset modprobe -r/+ qmi_wwan timeout (per RESEARCH A6).",
    )

    # --- Phase 4 destructive actions: signal floors (RELOAD_DATA, per B-03) ---
    #
    # Migrated from module-level Final constants in policy/transitions.py
    # (Plan 04-04 Task 3 deletes those). RELOAD_DATA so SIGHUP can retune
    # per cohort without daemon restart; defaults are RECOVERY_SPEC §6.1
    # verbatim. is_signal_below_gate(snap, config) reads these.

    signal_rsrp_floor_dbm: int = Field(
        default=-110,
        json_schema_extra=RELOAD_DATA,
        description="RECOVERY_SPEC §6.1 RSRP floor for rf_blocked (per B-03).",
    )
    signal_rsrq_floor_db: float = Field(
        default=-15.0,
        json_schema_extra=RELOAD_DATA,
        description="RECOVERY_SPEC §6.1 RSRQ floor for rf_blocked (per B-03).",
    )
    signal_snr_floor_db: float = Field(
        default=0.0,
        json_schema_extra=RELOAD_DATA,
        description="RECOVERY_SPEC §6.1 SNR floor for rf_blocked (per B-03).",
    )

    # --- Phase 4 destructive actions: ladder ceilings (RELOAD_DATA, per B-01) ---
    #
    # RECOVERY_SPEC §4.1 escalation ladder: SOFT_RESET (rung 1) -> MODEM_RESET
    # (rung 2) -> USB_RESET (rung 3) -> "skip:exhausted". Per-action counters
    # accumulate; at-or-above ceiling promotes to the next rung. Decision
    # table stays flat ((category, detail) -> base ActionKind); policy/ladder.py
    # owns rung selection. ge=1 -- a ceiling of 0 would short-circuit progression.

    max_soft: int = Field(
        default=3,
        ge=1,
        json_schema_extra=RELOAD_DATA,
        description="RECOVERY_SPEC §4.1 ladder ceiling for SOFT_RESET (per B-01).",
    )
    max_modem: int = Field(
        default=2,
        ge=1,
        json_schema_extra=RELOAD_DATA,
        description="RECOVERY_SPEC §4.1 ladder ceiling for MODEM_RESET (per B-01).",
    )
    max_usb: int = Field(
        default=1,
        ge=1,
        json_schema_extra=RELOAD_DATA,
        description="RECOVERY_SPEC §4.1 ladder ceiling for USB_RESET (per B-01).",
    )

    # --- Webhook (RELOAD_DATA) ---

    webhook_url: str | None = Field(
        default=None,
        json_schema_extra=RELOAD_DATA,
    )
    webhook_allow_http: bool = Field(
        default=False,
        json_schema_extra=RELOAD_DATA,
        description="NFR-33: webhook URL must be https unless this is true.",
    )
    webhook_dedup_seconds: int = Field(
        default=60,
        ge=0,
        json_schema_extra=RELOAD_DATA,
        description="M-2: per-(modem, transition) coalescing window.",
    )
    webhook_max_retries: int = Field(
        default=3,
        ge=0,
        json_schema_extra=RELOAD_DATA,
    )

    # --- Maintenance / dry-run (RELOAD_DATA) ---

    maintenance_max_seconds: int = Field(
        default=8 * 3600,
        ge=1,
        le=24 * 3600,
        json_schema_extra=RELOAD_DATA,
        description="FR-50.2: max 8h hard cap on `ctl maintenance on --duration`.",
    )
    dry_run: bool = Field(
        default=False,
        json_schema_extra=RELOAD_DATA,
        description="FR-28: global dry-run toggle.",
    )

    # --- Validators ---

    @field_validator("webhook_url")
    @classmethod
    def _validate_webhook_url_scheme(cls, v: str | None) -> str | None:
        """NFR-33: must be a valid http/https URL with a non-empty host."""
        if v is None:
            return None
        parts = urlsplit(v)
        if parts.scheme not in ("http", "https"):
            raise ValueError(f"webhook_url must use http or https scheme; got {parts.scheme!r}")
        if not parts.netloc:
            raise ValueError("webhook_url must include a host (netloc is empty)")
        if not parts.hostname:
            raise ValueError("webhook_url has an empty hostname")
        return v

    @model_validator(mode="after")
    def _validate_webhook_http_allowed(self) -> Settings:
        """NFR-33: http:// URLs require webhook_allow_http=True."""
        if (
            self.webhook_url is not None
            and self.webhook_url.startswith("http://")
            and not self.webhook_allow_http
        ):
            raise ValueError(
                "webhook_url uses http:// but webhook_allow_http is False (NFR-33); "
                "set SPARK_MODEM_WEBHOOK_ALLOW_HTTP=true to allow plain HTTP"
            )
        return self

    def resolve_hmac_secret_path(self) -> Path:
        """L-02: systemd 247+ sets CREDENTIALS_DIRECTORY; fall back to /etc/.../hmac-secret.

        Single file on disk serves both worlds: the LoadCredential= directive
        in spark-modem-watchdog.service points at the same path the fallback
        reads directly. On Ubuntu 20.04 / systemd 245 (PROJECT.md Hardware
        target) CREDENTIALS_DIRECTORY is unset and we fall back to /etc/.

        Reads os.environ at call time, not at construction (Settings.frozen=True
        does not cache env lookups; LoadCredential populates the env at unit
        start, which is AFTER Settings was first built in the test path).
        """
        creddir = os.environ.get("CREDENTIALS_DIRECTORY")
        if creddir:
            return Path(creddir) / "spark-modem-watchdog.hmac-secret"
        return Path("/etc/spark-modem-watchdog/hmac-secret")

    @classmethod
    def from_yaml_layer(cls, yaml_dict: dict[str, Any]) -> Settings:
        """Construct Settings with YAML-layer values; env+flags then override.

        Caller pattern:
            yaml_layer = load_yaml_layer('/etc/spark-modem-watchdog/conf.d/')
            settings = Settings.from_yaml_layer(yaml_layer)
            # Then CLI flags can override via Settings.model_copy(update={...}).
        """
        return cls(**yaml_dict)
