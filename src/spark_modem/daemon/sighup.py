"""SIGHUP transactional Settings swap (L-03 / Pattern 10).

When SIGHUP arrives the daemon rebuilds Settings from env + YAML, diffs
against the current frozen instance, and:

  * If any RELOAD_RESTART field changed (state_root, run_dir,
    events_log_path, metrics_socket_path, startup_delay_seconds),
    refuse the reload — emit a structured ``restart_required`` log
    record listing the offending fields and keep the old Settings.
    The daemon does NOT silently apply some and reject others; the
    swap is atomic at the field-set level.

  * On RELOAD_DATA-only changes, atomic-swap the cycle driver's
    ``self._settings`` reference. Side effects:
      - DnsCache re-resolve when ``webhook_url`` changed (W-02 honored
        without 60 s timer wait).
      - Carrier-table re-read on path-content sha256 change is owned
        by the consumer (Plan 03-07); this module only touches Settings
        + DNS.

The cycle driver reads ``self._settings`` once at the start of each
cycle so a swap is naturally atomic at cycle boundary — a cycle never
observes a half-swapped Settings.

``carriers_yaml_path`` is RELOAD_DATA — operators edit the carrier
table without restarting (FR-33). The daemon's actual file-content
re-read is downstream; the SIGHUP handler emits a wake signal so the
next cycle picks up.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

from spark_modem.config.reload_marker import restart_required_fields
from spark_modem.config.settings import Settings

logger = logging.getLogger(__name__)


class _SettingsRefProto(Protocol):
    """Single-cell mutable container around the current frozen Settings.

    The cycle driver reads ``self._settings`` once per cycle from the
    same reference; ``set`` swaps the cell atomically at cycle boundary
    (no concurrent reader inside the swap call because the cycle driver
    is on the same event loop and the swap happens between cycles).
    """

    def get(self) -> Settings: ...

    def set(self, new: Settings) -> None: ...


class _DnsCacheProto(Protocol):
    """W-02 DnsCache surface — force-refresh on webhook URL change."""

    async def resolve(self, host: str) -> str | None: ...


class SighupSwapper:
    """Transactional Settings swap with RELOAD_RESTART refusal (L-03).

    ``settings_factory`` is a zero-arg callable that builds a fresh
    Settings instance from env + YAML — the same path Phase 1's
    Settings construction uses. Tests inject a recording callable that
    returns synthetic Settings; production wires the real env+YAML
    builder.
    """

    def __init__(
        self,
        *,
        settings_ref: _SettingsRefProto,
        settings_factory: Callable[[], Settings],
        dns_cache: _DnsCacheProto | None = None,
    ) -> None:
        self._settings_ref = settings_ref
        self._settings_factory = settings_factory
        self._dns_cache = dns_cache
        self._restart_required_fields: frozenset[str] = restart_required_fields(Settings)

    async def try_apply_reload(self) -> bool:
        """Try to apply a SIGHUP-driven Settings reload.

        Returns:
            True  — swap succeeded (RELOAD_DATA-only diff applied).
            False — swap refused (RELOAD_RESTART field changed) OR
                    settings_factory raised (kept old Settings).
        """
        try:
            new = self._settings_factory()
        except Exception:
            logger.exception("sighup: settings_factory failed; keeping old Settings")
            return False

        old = self._settings_ref.get()
        diff = _diff_field_set(old, new)
        if not diff:
            # No-op SIGHUP — common in production (operator just wants
            # to confirm the daemon is responsive; nothing to apply).
            return True

        offenders = diff & self._restart_required_fields
        if offenders:
            logger.warning(
                "sighup: restart_required fields changed=%s; keeping old Settings",
                sorted(offenders),
            )
            return False

        # RELOAD_DATA-only change — swap the reference atomically.
        self._settings_ref.set(new)

        # Side effect: webhook URL change forces DnsCache re-resolve.
        if "webhook_url" in diff and self._dns_cache is not None and new.webhook_url:
            from urllib.parse import urlsplit  # noqa: PLC0415

            host = urlsplit(new.webhook_url).hostname
            if host:
                try:
                    await self._dns_cache.resolve(host)
                except Exception:
                    logger.exception("sighup: dns_cache.resolve failed host=%s", host)

        logger.info("sighup: reload applied; changed_fields=%s", sorted(diff))
        return True


def _diff_field_set(old: Settings, new: Settings) -> frozenset[str]:
    """Return the set of field names whose value differs between two Settings.

    Settings is ``frozen=True`` (Phase 1 invariant) so identity comparison
    is safe — every field is a primitive or another frozen pydantic model.
    """
    out: set[str] = set()
    old_dump = old.model_dump()
    new_dump = new.model_dump()
    for key in old_dump.keys() | new_dump.keys():
        if old_dump.get(key) != new_dump.get(key):
            out.add(key)
    return frozenset(out)
