"""FakeDNSResolver -- canned IPs for hardware-free webhook tests.

The real `webhook/dns.py` (Plan 02-08) wraps `loop.getaddrinfo()` with a
60 s refresh + 600 s stale-fallback. This fake satisfies the same
`async resolve(host, loop) -> str | None` surface and lets tests inject
deterministic resolve / fail-once / no-DNS sequences.

`set_fail_next()` flips a one-shot flag: the next resolve returns None,
then the flag clears and subsequent calls return `_ip` again. This matches
the W-02 stale-fallback contract: a single transient resolve failure must
not strand the poster.
"""

from __future__ import annotations


class FakeDNSResolver:
    """Returns a canned IP; supports one-shot fail and persistent no-DNS modes."""

    def __init__(self, *, canned_ip: str = "192.0.2.1") -> None:
        self._ip: str | None = canned_ip
        self._fail_next: bool = False

    async def resolve(self, host: str, loop: object | None = None) -> str | None:
        """Return canned_ip, or None if `_fail_next` was set or `_ip` is None."""
        del host, loop  # call-surface parity with real DnsCache.resolve
        if self._fail_next:
            self._fail_next = False
            return None
        return self._ip

    def set_fail_next(self) -> None:
        """Cause exactly the next resolve() call to return None."""
        self._fail_next = True

    def set_canned_ip(self, ip: str | None) -> None:
        """Set the canned IP returned by future resolves (None == always fail)."""
        self._ip = ip
