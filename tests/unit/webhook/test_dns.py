"""Tests for webhook.dns.DnsCache — refresh + stale-window fallback (W-02)."""

from __future__ import annotations

from asyncio.base_events import BaseEventLoop

import pytest

from spark_modem.webhook.dns import DnsCache
from tests.fakes.clock import FakeClock

_HOST = "noc.example.test"
_IP_V1 = "192.0.2.7"
_IP_V2 = "198.51.100.42"


class _Counter:
    def __init__(self) -> None:
        self.calls: int = 0


def _patch_getaddrinfo(
    monkeypatch: pytest.MonkeyPatch,
    *,
    return_ip: str | None = _IP_V1,
    raise_oserror: bool = False,
    counter: _Counter | None = None,
) -> _Counter:
    """Replace BaseEventLoop.getaddrinfo with a deterministic stub.

    BaseEventLoop is the concrete superclass of every event-loop impl
    that ships with CPython (Selector, Proactor, …); the abstract base
    only stubs the method. Patching here intercepts the call that
    DnsCache.resolve makes via ``loop.getaddrinfo`` regardless of which
    concrete loop the test event loop ends up being.

    Returns the counter (creating one if not provided) so tests can
    assert on invocation counts.
    """
    cnt = counter if counter is not None else _Counter()

    async def fake_getaddrinfo(
        self: object,
        host: str,
        port: int,
        *args: object,
        **kwargs: object,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        del self, host, port, args, kwargs
        cnt.calls += 1
        if raise_oserror:
            raise OSError("simulated resolver failure")
        if return_ip is None:  # caller wants OSError-equivalent miss
            raise OSError("simulated resolver failure")
        return [(2, 1, 6, "", (return_ip, 443))]

    monkeypatch.setattr(
        BaseEventLoop,
        "getaddrinfo",
        fake_getaddrinfo,
        raising=True,
    )
    return cnt


async def test_resolve_returns_cached_ip_within_refresh_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First call resolves; second call within refresh_interval reuses cache."""
    clock = FakeClock()
    cnt = _patch_getaddrinfo(monkeypatch, return_ip=_IP_V1)
    cache = DnsCache(clock=clock, refresh_interval=60.0, stale_max=600.0)

    ip_a = await cache.resolve(_HOST)
    ip_b = await cache.resolve(_HOST)

    assert ip_a == _IP_V1
    assert ip_b == _IP_V1
    assert cnt.calls == 1  # second call hit the cache


async def test_resolve_refreshes_after_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Past refresh_interval, getaddrinfo is invoked again."""
    clock = FakeClock()
    cnt = _patch_getaddrinfo(monkeypatch, return_ip=_IP_V1)
    cache = DnsCache(clock=clock, refresh_interval=60.0, stale_max=600.0)

    await cache.resolve(_HOST)
    assert cnt.calls == 1

    clock.advance(61.0)
    await cache.resolve(_HOST)
    assert cnt.calls == 2


async def test_resolve_returns_stale_on_failure_within_stale_max(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolver failure within stale_max returns the previously-cached IP."""
    clock = FakeClock()
    cnt = _patch_getaddrinfo(monkeypatch, return_ip=_IP_V1)
    cache = DnsCache(clock=clock, refresh_interval=60.0, stale_max=600.0)

    # Populate the cache.
    assert await cache.resolve(_HOST) == _IP_V1
    assert cnt.calls == 1

    # Now flip the resolver to fail and advance past refresh_interval but
    # within stale_max.
    _patch_getaddrinfo(monkeypatch, raise_oserror=True, counter=cnt)
    clock.advance(120.0)

    # Stale-but-OK: returns the previously-cached IP.
    ip = await cache.resolve(_HOST)
    assert ip == _IP_V1
    assert cnt.calls == 2  # one fresh resolve + one failed retry


async def test_resolve_returns_none_after_stale_max(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Past stale_max with persistent failures, the cache returns None."""
    clock = FakeClock()
    cnt = _patch_getaddrinfo(monkeypatch, return_ip=_IP_V1)
    cache = DnsCache(clock=clock, refresh_interval=60.0, stale_max=600.0)

    assert await cache.resolve(_HOST) == _IP_V1
    assert cnt.calls == 1

    _patch_getaddrinfo(monkeypatch, raise_oserror=True, counter=cnt)
    clock.advance(601.0)

    ip = await cache.resolve(_HOST)
    assert ip is None
    assert cnt.calls == 2


async def test_resolve_returns_none_on_first_call_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the first resolve fails (no cache yet), return None — no fall-back."""
    clock = FakeClock()
    cnt = _patch_getaddrinfo(monkeypatch, raise_oserror=True)
    cache = DnsCache(clock=clock, refresh_interval=60.0, stale_max=600.0)

    ip = await cache.resolve(_HOST)
    assert ip is None
    assert cnt.calls == 1


async def test_resolve_recovers_after_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient failure followed by a successful resolve refreshes the cache."""
    clock = FakeClock()
    cnt = _patch_getaddrinfo(monkeypatch, return_ip=_IP_V1)
    cache = DnsCache(clock=clock, refresh_interval=60.0, stale_max=600.0)

    assert await cache.resolve(_HOST) == _IP_V1

    # Failure within stale window -> stale.
    _patch_getaddrinfo(monkeypatch, raise_oserror=True, counter=cnt)
    clock.advance(120.0)
    assert await cache.resolve(_HOST) == _IP_V1

    # Resolver recovers with a new IP -> new cache.
    _patch_getaddrinfo(monkeypatch, return_ip=_IP_V2, counter=cnt)
    clock.advance(1.0)
    assert await cache.resolve(_HOST) == _IP_V2


async def test_default_refresh_interval_and_stale_max() -> None:
    """Defaults are 60s refresh + 600s stale_max (W-02)."""
    cache = DnsCache()
    assert cache._refresh_interval == 60.0
    assert cache._stale_max == 600.0


async def test_resolve_uses_real_loop_getaddrinfo_on_localhost() -> None:
    """End-to-end test against a known-static name, no monkeypatch.

    Localhost is guaranteed to resolve on every CI / dev environment without
    requiring any real DNS server. This is the only test that exercises the
    real loop.getaddrinfo path.
    """
    cache = DnsCache(refresh_interval=60.0, stale_max=600.0)
    ip = await cache.resolve("localhost")
    # Either 127.0.0.1 (IPv4) or ::1 (IPv6) is acceptable; the contract is
    # only that we got a non-None string back.
    assert ip is not None
    assert isinstance(ip, str)
    assert len(ip) > 0
