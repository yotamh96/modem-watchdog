"""L-02 unit tests for Settings.resolve_hmac_secret_path()."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from spark_modem.config.settings import Settings


def test_fallback_path_when_credentials_directory_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # L-02: systemd 245 fallback
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    settings = Settings()
    assert settings.resolve_hmac_secret_path() == Path(
        "/etc/spark-modem-watchdog/hmac-secret"
    )


def test_credentials_directory_path_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # L-02: systemd 247+ LoadCredential populated path
    monkeypatch.setenv(
        "CREDENTIALS_DIRECTORY",
        "/run/credentials/spark-modem-watchdog.service",
    )
    settings = Settings()
    assert settings.resolve_hmac_secret_path() == Path(
        "/run/credentials/spark-modem-watchdog.service/spark-modem-watchdog.hmac-secret"
    )


def test_reads_env_at_call_time_not_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # frozen=True does not cache os.environ; method reads on each call.
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    settings = Settings()
    first = settings.resolve_hmac_secret_path()
    assert first == Path("/etc/spark-modem-watchdog/hmac-secret")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", "/foo")
    second = settings.resolve_hmac_secret_path()
    assert second == Path("/foo/spark-modem-watchdog.hmac-secret")
