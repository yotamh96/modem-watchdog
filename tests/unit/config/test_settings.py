"""Tests for spark_modem.config.settings — pydantic-settings BaseSettings."""

from __future__ import annotations

import pydantic_settings
import pytest
from pydantic import ValidationError

from spark_modem.config.reload_marker import restart_required_fields
from spark_modem.config.settings import Settings


def test_pydantic_settings_importable() -> None:
    assert pydantic_settings.__version__


def test_settings_default_backoff_seconds() -> None:
    s = Settings()
    assert s.backoff_seconds == 300


def test_settings_default_ladder_min_interval() -> None:
    s = Settings()
    assert s.ladder_min_interval_seconds == 90


def test_settings_default_healthy_streak_decay_k() -> None:
    s = Settings()
    assert s.healthy_streak_decay_k == 10


def test_settings_default_webhook_url_none() -> None:
    s = Settings()
    assert s.webhook_url is None


def test_settings_default_webhook_allow_http_false() -> None:
    s = Settings()
    assert s.webhook_allow_http is False


def test_settings_default_webhook_dedup_seconds() -> None:
    s = Settings()
    assert s.webhook_dedup_seconds == 60


def test_settings_default_maintenance_max_seconds() -> None:
    s = Settings()
    assert s.maintenance_max_seconds == 8 * 3600


def test_settings_default_state_root() -> None:
    s = Settings()
    assert s.state_root == "/var/lib/spark-modem-watchdog"


def test_settings_default_run_dir() -> None:
    s = Settings()
    assert s.run_dir == "/run/spark-modem-watchdog"


def test_settings_default_events_log_path() -> None:
    s = Settings()
    assert s.events_log_path == "/var/log/spark-modem-watchdog/events.jsonl"


def test_settings_default_carriers_yaml_path() -> None:
    s = Settings()
    assert s.carriers_yaml_path == "/etc/spark-modem-watchdog/conf.d/00-carriers.yaml"


def test_settings_reads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARK_MODEM_BACKOFF_SECONDS", "600")
    s = Settings()
    assert s.backoff_seconds == 600


def test_settings_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARK_MODEM_HEALTHY_STREAK_DECAY_K", "20")
    s = Settings()
    assert s.healthy_streak_decay_k == 20


def test_settings_state_root_has_reload_restart_marker() -> None:
    restart = restart_required_fields(Settings)
    assert "state_root" in restart


def test_settings_backoff_seconds_not_in_restart_required() -> None:
    restart = restart_required_fields(Settings)
    assert "backoff_seconds" not in restart


def test_settings_restart_required_fields_topology_set() -> None:
    restart = restart_required_fields(Settings)
    # All topology-affecting paths must require restart
    assert "state_root" in restart
    assert "run_dir" in restart
    assert "events_log_path" in restart
    assert "metrics_socket_path" in restart


def test_settings_webhook_url_rejects_non_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARK_MODEM_WEBHOOK_URL", "ftp://bad.example.com")
    with pytest.raises(ValidationError):
        Settings()


def test_settings_webhook_url_accepts_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARK_MODEM_WEBHOOK_URL", "https://example.com/hook")
    s = Settings()
    assert s.webhook_url == "https://example.com/hook"


def test_settings_webhook_url_accepts_http_when_flag_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARK_MODEM_WEBHOOK_URL", "http://internal.example.com/hook")
    monkeypatch.setenv("SPARK_MODEM_WEBHOOK_ALLOW_HTTP", "true")
    s = Settings()
    assert s.webhook_url == "http://internal.example.com/hook"


def test_settings_from_yaml_layer_overlays_defaults() -> None:
    yaml_dict = {"backoff_seconds": 999}
    s = Settings.from_yaml_layer(yaml_dict)
    assert s.backoff_seconds == 999
    # Other defaults unchanged
    assert s.webhook_url is None


def test_settings_frozen_immutable() -> None:
    s = Settings()
    with pytest.raises(ValidationError):
        s.backoff_seconds = 999  # type: ignore[misc]
