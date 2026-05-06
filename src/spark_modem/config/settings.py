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

from typing import Any

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
    healthy_streak_decay_k: int = Field(
        default=10,
        ge=1,
        json_schema_extra=RELOAD_DATA,
        description="ADR-0006 K consecutive Healthy cycles before counters decay.",
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
        """NFR-33: must start with http:// or https://."""
        if v is None:
            return None
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("webhook_url must start with http:// or https://")
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

    @classmethod
    def from_yaml_layer(cls, yaml_dict: dict[str, Any]) -> Settings:
        """Construct Settings with YAML-layer values; env+flags then override.

        Caller pattern:
            yaml_layer = load_yaml_layer('/etc/spark-modem-watchdog/conf.d/')
            settings = Settings.from_yaml_layer(yaml_layer)
            # Then CLI flags can override via Settings.model_copy(update={...}).
        """
        return cls(**yaml_dict)
