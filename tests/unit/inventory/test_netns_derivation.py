"""Unit tests for netns derivation from sysfs.

Open Question 4 (RESEARCH.md): three options exist for reading the
netns of a cdc-wdm worker. We pick option-(a) — read the
``<usb_dev_path>/.../net/wwan*/device/ns/net`` symlink and resolve
the inode to a name in ``/var/run/netns/``. On the bench Jetson the
link is absent (single-namespace setup) → derive_ns returns None.

PITFALLS §6.2 reminder: this function ONLY READS sysfs; ``setns()``
is NEVER called from the asyncio loop. QmiWrapper's netns prepend
(``ip netns exec <ns>``) does its own setns in a forked child.

Tests use ``netns_root`` parameter injection (testable defaults per
Phase 1/2 convention) to swap ``/var/run/netns/`` for tmp_path —
keeps tests cross-platform where possible.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from spark_modem.inventory.netns import derive_ns

_SKIP_WIN = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX symlink semantics required for netns derivation tests",
)


def test_returns_none_when_usb_path_does_not_exist(tmp_path: Path) -> None:
    """A non-existent usb_dev_path returns None (no rglob matches)."""
    bogus = tmp_path / "does-not-exist"
    assert derive_ns(bogus) is None


def test_returns_none_when_wwan_dir_absent(tmp_path: Path) -> None:
    """A usb_dev_path with no net/wwan* children returns None."""
    (tmp_path / "intf" / "usbmisc" / "cdc-wdm0").mkdir(parents=True)
    # Note: no net/wwan* directory.
    assert derive_ns(tmp_path) is None


@_SKIP_WIN
def test_returns_none_when_ns_link_absent(tmp_path: Path) -> None:
    """A wwan dir without device/ns/net link returns None (bench Jetson case)."""
    wwan = tmp_path / "intf" / "net" / "wwan0"
    wwan.mkdir(parents=True)
    # No device/ns/net symlink — single-namespace bench Jetson reality.
    assert derive_ns(tmp_path) is None


@_SKIP_WIN
def test_returns_none_when_link_target_not_named_netns(tmp_path: Path) -> None:
    """ns/net link pointing to net:[<inode>] for an inode not in /var/run/netns → None."""
    wwan = tmp_path / "intf" / "net" / "wwan0"
    device_dir = wwan / "device"
    ns_dir = device_dir / "ns"
    ns_dir.mkdir(parents=True)
    ns_link = ns_dir / "net"
    # Point to a fictitious inode that won't match anything in netns_root.
    ns_link.symlink_to("net:[99999999]")
    empty_netns_root = tmp_path / "var-run-netns"
    empty_netns_root.mkdir()
    assert derive_ns(tmp_path, netns_root=empty_netns_root) is None


@_SKIP_WIN
def test_returns_name_when_netns_inode_matches(tmp_path: Path) -> None:
    """ns/net link inode matches a file in netns_root → return that file's name."""
    wwan = tmp_path / "intf" / "net" / "wwan0"
    device_dir = wwan / "device"
    ns_dir = device_dir / "ns"
    ns_dir.mkdir(parents=True)

    # Create a real file in the fake netns_root; capture its inode.
    netns_root = tmp_path / "var-run-netns"
    netns_root.mkdir()
    target_ns = netns_root / "line1"
    target_ns.write_text("placeholder")
    inode = target_ns.stat().st_ino

    ns_link = ns_dir / "net"
    ns_link.symlink_to(f"net:[{inode}]")

    assert derive_ns(tmp_path, netns_root=netns_root) == "line1"


@_SKIP_WIN
def test_returns_none_when_link_target_malformed(tmp_path: Path) -> None:
    """ns/net link pointing to a non net:[...] string returns None."""
    wwan = tmp_path / "intf" / "net" / "wwan0"
    device_dir = wwan / "device"
    ns_dir = device_dir / "ns"
    ns_dir.mkdir(parents=True)
    ns_link = ns_dir / "net"
    ns_link.symlink_to("not-a-netns-target")
    assert derive_ns(tmp_path) is None


@_SKIP_WIN
def test_returns_none_when_link_target_inode_unparseable(tmp_path: Path) -> None:
    """net:[<not-an-int>] returns None gracefully."""
    wwan = tmp_path / "intf" / "net" / "wwan0"
    device_dir = wwan / "device"
    ns_dir = device_dir / "ns"
    ns_dir.mkdir(parents=True)
    ns_link = ns_dir / "net"
    ns_link.symlink_to("net:[abc]")
    assert derive_ns(tmp_path) is None


@_SKIP_WIN
def test_returns_none_when_netns_root_does_not_exist(tmp_path: Path) -> None:
    """Production /var/run/netns absent → None (bench Jetson default)."""
    wwan = tmp_path / "intf" / "net" / "wwan0"
    device_dir = wwan / "device"
    ns_dir = device_dir / "ns"
    ns_dir.mkdir(parents=True)
    ns_link = ns_dir / "net"
    ns_link.symlink_to("net:[12345]")
    nonexistent_netns_root = tmp_path / "absent-dir"
    assert derive_ns(tmp_path, netns_root=nonexistent_netns_root) is None
