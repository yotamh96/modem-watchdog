"""netns derivation for a USB device's netns assignment (E-05).

Open Question 4 (RESEARCH.md): three options exist for reading the
netns of a cdc-wdm worker. We pick option-(a) — read the symlink

    <usb_dev_path>/.../net/wwan*/device/ns/net

(sysfs convention: ``/sys/class/net/<iface>/device/ns/net`` is a
symlink to ``net:[<inode>]``); resolve the inode against
``/var/run/netns/`` (root-owned dir whose entries are bind-mounts of
named netns) and return the matching filename.

On the bench Jetson the link is absent (single-namespace setup) →
``derive_ns`` returns ``None``. Production fleets that wrap each
modem in a per-line netns will see the real name. The descriptor's
``ns: str | None`` field already accepts both.

PITFALLS §6.2 reminder: this function ONLY READS sysfs; the daemon
NEVER calls ``setns()`` from the asyncio loop. The QmiWrapper netns
prepend (``ip netns exec <ns>``) does its own setns in a forked
child process — the daemon's loop stays in the host namespace.

Same shape as ``inventory/sysfs.py``'s ``_find_cdc_wdm`` /
``_find_wwan_iface`` static helpers (PATTERNS.md): nullable return,
skip-on-missing semantics, no exceptions raised for absent files.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Final

_DEFAULT_NETNS_ROOT: Final[Path] = Path("/var/run/netns")


def derive_ns(
    usb_dev_path: Path,
    *,
    netns_root: Path | None = None,
) -> str | None:
    """Return the netns name for the cdc-wdm under ``usb_dev_path``, or None.

    Walks ``<usb_dev_path>/.../net/wwan*`` for the device's wwan
    interface; reads the ``device/ns/net`` symlink (sysfs convention);
    parses ``net:[<inode>]`` from the link target; matches the inode
    against the entries of ``netns_root`` (default ``/var/run/netns``).

    On any IO error, missing path, malformed link target, or absent
    netns_root, returns ``None``. The bench Jetson is single-namespace,
    so ``None`` is the expected default.

    Parameters
    ----------
    usb_dev_path
        Resolved USB device path (e.g. ``/sys/bus/usb/devices/2-3.1.1``).
    netns_root
        Override for ``/var/run/netns`` — testable default per Phase 1/2
        convention; tests inject ``tmp_path`` instead of patching imports.
    """
    root = netns_root if netns_root is not None else _DEFAULT_NETNS_ROOT

    if not usb_dev_path.is_dir():
        return None

    # Mirrors SysfsInventory._find_wwan_iface (PATTERNS.md analog).
    for net in usb_dev_path.rglob("net/wwan*"):
        if not (net.is_dir() or net.is_symlink()):
            continue
        ns_link = net / "device" / "ns" / "net"
        if not ns_link.is_symlink():
            return None
        try:
            target = ns_link.readlink()
        except (FileNotFoundError, OSError, NotADirectoryError):
            return None
        return _resolve_netns_name(target, netns_root=root)
    return None


def _resolve_netns_name(ns_link_target: Path, *, netns_root: Path) -> str | None:
    """Match a ``net:[<inode>]`` link target to a name in ``netns_root``.

    The link target shape is ``net:[<inode>]`` where ``<inode>`` is the
    numeric netns inode the kernel assigned. ``ip netns add foo`` creates
    ``/var/run/netns/foo`` as a bind-mount of that inode; matching by
    ``stat().st_ino`` is the canonical way to recover the name from the
    inode without parsing ``ip netns identify`` (subprocess-free).

    Returns ``None`` for a malformed target, an unparseable inode, an
    absent ``netns_root``, or no matching entry.
    """
    target_str = str(ns_link_target)
    if not target_str.startswith("net:["):
        return None
    inode_str = target_str[len("net:[") :].rstrip("]")
    try:
        inode = int(inode_str)
    except ValueError:
        return None

    if not netns_root.is_dir():
        return None

    for entry in netns_root.iterdir():
        with contextlib.suppress(FileNotFoundError, OSError):
            if entry.stat().st_ino == inode:
                return entry.name
    return None
