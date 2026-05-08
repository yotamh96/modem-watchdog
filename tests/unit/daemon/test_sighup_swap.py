"""Unit tests for SighupSwapper transactional Settings swap (L-03)."""

from __future__ import annotations

from spark_modem.config.settings import Settings
from spark_modem.daemon.sighup import SighupSwapper

# ---------------------------------------------------------------------------
# Helpers — recording cell + recording DnsCache
# ---------------------------------------------------------------------------


class _SettingsCell:
    def __init__(self, initial: Settings) -> None:
        self._value = initial
        self.set_calls: list[Settings] = []

    def get(self) -> Settings:
        return self._value

    def set(self, new: Settings) -> None:
        self._value = new
        self.set_calls.append(new)


class _RecordingDnsCache:
    def __init__(self) -> None:
        self.resolve_calls: list[str] = []

    async def resolve(self, host: str) -> str | None:
        self.resolve_calls.append(host)
        return "203.0.113.1"


def _build_settings(**overrides: object) -> Settings:
    """Construct a Settings with the requested field overrides."""
    base = {
        "webhook_url": "https://example.org/hook",
        "webhook_allow_http": False,
        "backoff_seconds": 300,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_restart_required_field_changed_returns_false() -> None:
    """Changing state_root (RELOAD_RESTART) → reload refused, ref unchanged."""
    old = _build_settings(state_root="/var/lib/spark-modem-watchdog")
    new = _build_settings(state_root="/different/state-root")
    cell = _SettingsCell(old)
    swapper = SighupSwapper(
        settings_ref=cell,
        settings_factory=lambda: new,
        dns_cache=None,
    )
    applied = await swapper.try_apply_reload()
    assert applied is False
    assert cell.get() is old
    assert cell.set_calls == []


async def test_data_field_changed_returns_true_and_swaps_ref() -> None:
    """Changing webhook_url (RELOAD_DATA) → reload applied, ref swapped."""
    old = _build_settings(webhook_url="https://old.example.org/hook")
    new = _build_settings(webhook_url="https://new.example.org/hook")
    cell = _SettingsCell(old)
    dns_cache = _RecordingDnsCache()
    swapper = SighupSwapper(
        settings_ref=cell,
        settings_factory=lambda: new,
        dns_cache=dns_cache,
    )
    applied = await swapper.try_apply_reload()
    assert applied is True
    assert cell.get() is new
    assert len(cell.set_calls) == 1


async def test_dns_resolve_called_on_webhook_url_change() -> None:
    """webhook_url change triggers dns_cache.resolve(new_host)."""
    old = _build_settings(webhook_url="https://old.example.org/hook")
    new = _build_settings(webhook_url="https://new.example.org/hook")
    cell = _SettingsCell(old)
    dns_cache = _RecordingDnsCache()
    swapper = SighupSwapper(
        settings_ref=cell,
        settings_factory=lambda: new,
        dns_cache=dns_cache,
    )
    await swapper.try_apply_reload()
    assert dns_cache.resolve_calls == ["new.example.org"]


async def test_settings_factory_failure_keeps_old_returns_false() -> None:
    """If factory raises, swap refused; ref unchanged; returns False."""
    old = _build_settings()
    cell = _SettingsCell(old)

    def boom() -> Settings:
        raise RuntimeError("synthetic env-parse failure")

    swapper = SighupSwapper(
        settings_ref=cell,
        settings_factory=boom,
        dns_cache=None,
    )
    applied = await swapper.try_apply_reload()
    assert applied is False
    assert cell.get() is old
    assert cell.set_calls == []
