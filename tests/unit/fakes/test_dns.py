"""Tests for tests.fakes.dns.FakeDNSResolver."""

from __future__ import annotations

from tests.fakes.dns import FakeDNSResolver


async def test_resolve_returns_canned_ip() -> None:
    dns = FakeDNSResolver(canned_ip="198.51.100.7")
    ip = await dns.resolve("example.com")
    assert ip == "198.51.100.7"


async def test_set_fail_next_is_one_shot() -> None:
    dns = FakeDNSResolver(canned_ip="192.0.2.1")
    dns.set_fail_next()
    assert await dns.resolve("example.com") is None
    # The flag self-clears: the call after a fail returns the canned IP again.
    assert await dns.resolve("example.com") == "192.0.2.1"


async def test_set_canned_ip_none_means_persistent_failure() -> None:
    dns = FakeDNSResolver()
    dns.set_canned_ip(None)
    assert await dns.resolve("example.com") is None
    assert await dns.resolve("example.com") is None


async def test_set_canned_ip_changes_returned_value() -> None:
    dns = FakeDNSResolver(canned_ip="192.0.2.1")
    assert await dns.resolve("example.com") == "192.0.2.1"
    dns.set_canned_ip("203.0.113.5")
    assert await dns.resolve("example.com") == "203.0.113.5"
