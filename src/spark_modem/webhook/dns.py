"""DnsCache — pre-resolves and refreshes the webhook host (W-02 / ADR-0011).

On daemon start (and on SIGHUP in Phase 3) the cache resolves the host
via ``loop.getaddrinfo`` (which runs in the default ThreadPoolExecutor —
it does NOT block the asyncio event-loop thread). The cached IP refreshes
every ``refresh_interval`` seconds; on resolve failure within
``stale_max`` seconds of the last success, the previous result is
returned ("stale-but-OK"). After ``stale_max`` the cache returns None and
the poster increments
``webhook_delivery_total{result="skipped_no_dns"}``.

Defaults match ADR-0011 / W-02: refresh every 60s; tolerate up to 600s
of resolver downtime before giving up.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from typing import Protocol

logger = logging.getLogger(__name__)


class ClockProto(Protocol):
    """Minimal monotonic-clock surface (matches FakeClock and clock.monotonic)."""

    def monotonic(self) -> float: ...


class DnsCache:
    """Pre-resolved DNS cache with refresh + stale-window fallback."""

    def __init__(
        self,
        *,
        clock: ClockProto | None = None,
        refresh_interval: float = 60.0,
        stale_max: float = 600.0,
    ) -> None:
        self._clock = clock
        self._refresh_interval = refresh_interval
        self._stale_max = stale_max
        self._ip: str | None = None
        self._expires_at: float = 0.0
        self._stale_until: float = 0.0

    def _now(self) -> float:
        return self._clock.monotonic() if self._clock is not None else time.monotonic()

    async def resolve(self, host: str) -> str | None:
        """Return a cached IP, refreshing via getaddrinfo when expired.

        Returns:
            The cached IP, the freshly-resolved IP, or None if the resolver
            has been failing for longer than ``stale_max`` seconds (or has
            never succeeded).
        """
        now = self._now()
        if self._ip is not None and now < self._expires_at:
            return self._ip
        try:
            loop = asyncio.get_running_loop()
            infos = await loop.getaddrinfo(
                host,
                443,
                type=socket.SOCK_STREAM,
            )
            # Each entry: (family, type, proto, canonname, sockaddr).
            # sockaddr[0] is the IP string for AF_INET / AF_INET6.
            ip = str(infos[0][4][0])
            self._ip = ip
            self._expires_at = now + self._refresh_interval
            self._stale_until = now + self._stale_max
            return self._ip
        except OSError:
            logger.warning("webhook_dns_resolve_failed host=%s", host)
            if self._ip is not None and now < self._stale_until:
                return self._ip
            return None
