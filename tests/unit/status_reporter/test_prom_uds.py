"""Linux-only AF_UNIX scrape integration tests for the Prom UDS exporter.

Tests in this module are skipped on Windows: the daemon production
target is Linux/aarch64, the wsgiref + asyncio.to_thread bridge is
fragile on Windows, and the test harness uses raw AF_UNIX sockets +
``socket.socket.connect`` which behaves slightly differently on
Win10 1803+ AF_UNIX.

Tests use ``tmp_path`` for the socket location so no
``/run/spark-modem-watchdog/`` write happens during ``pytest`` runs.
"""

from __future__ import annotations

import contextlib
import socket
import stat
import sys
import threading
from pathlib import Path

import pytest
from prometheus_client import Counter
from prometheus_client.registry import CollectorRegistry

from spark_modem.status_reporter.prom import _UnixWSGIServer, start_metrics_server

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="AF_UNIX socket scrape integration; production target is Linux.",
)


def _close_server(server: _UnixWSGIServer) -> None:
    """Idempotent cleanup helper."""
    with contextlib.suppress(Exception):
        server.shutdown()
    with contextlib.suppress(Exception):
        server.server_close()


def test_unix_wsgi_server_bind_initializes_server_name_and_port(
    tmp_path: Path,
) -> None:
    """Regression: _UnixWSGIServer.server_bind MUST assign server_name + server_port.

    Bench Jetson 2026-05-18: a daemon boot past fleet-triple preflight
    crashed in `_production_main` with::

        AttributeError: '_UnixWSGIServer' object has no attribute 'server_name'

    Root cause: `UnixStreamServer.server_bind` does a plain `socket.bind`
    and does NOT set `server_name` / `server_port` (the TCP path's
    `HTTPServer.server_bind` does, from `self.server_address[:2]`).
    `wsgiref.simple_server.setup_environ()` then reads `self.server_name`
    unconditionally → AttributeError.

    The integration test `tests/integration/test_production_main.py`
    monkeypatches `start_metrics_server` away (Generator self-eval blind
    spot — Anthropic harness research) so it cannot catch this. This
    unit test exercises the real bind path with NO socket connection,
    NO threading, NO scrape — just construct + assert + close.
    """
    sock_path = tmp_path / "regression.sock"
    # Use start_metrics_server (the production caller) so the test exercises
    # the same bind path the daemon does — _UnixWSGIServer construction
    # triggers server_bind() via UnixStreamServer.__init__.
    server = start_metrics_server(sock_path, registry=CollectorRegistry(auto_describe=False))
    try:
        # The attributes MUST exist after server_bind() (which is called
        # automatically by UnixStreamServer.__init__ when
        # bind_and_activate=True, the default). Values are nonsense for
        # UDS but the wsgiref handler does not consume them.
        assert hasattr(server, "server_name"), (
            "_UnixWSGIServer.server_bind must assign server_name before "
            "setup_environ() reads it (regression — bench Jetson 2026-05-18)"
        )
        assert hasattr(server, "server_port"), (
            "_UnixWSGIServer.server_bind must assign server_port before "
            "setup_environ() reads it (regression — bench Jetson 2026-05-18)"
        )
        # Sanity-check the placeholder values are sensible types.
        assert isinstance(server.server_name, str)
        assert isinstance(server.server_port, int)
    finally:
        _close_server(server)


def test_start_metrics_server_creates_socket(tmp_path: Path) -> None:
    """start_metrics_server creates the socket with mode 0o660.

    The 0o660 bits gate scraping to the ``adm`` group — non-adm
    processes on the box cannot read metrics (T-02-07-01 mitigation).
    """
    sock_path = tmp_path / "metrics.sock"
    coll = CollectorRegistry(auto_describe=False)

    server = start_metrics_server(sock_path, registry=coll)
    try:
        assert sock_path.exists()
        mode_bits = sock_path.stat().st_mode & 0o777
        assert mode_bits == 0o660
        assert stat.S_ISSOCK(sock_path.stat().st_mode)
    finally:
        _close_server(server)


def test_stale_socket_cleaned_on_restart(tmp_path: Path) -> None:
    """PITFALLS §13.3: a leftover socket file from a crashed run is unlinked."""
    sock_path = tmp_path / "metrics.sock"
    # Simulate a stale socket file from a prior crashed run.
    sock_path.write_bytes(b"")
    assert sock_path.exists()

    coll = CollectorRegistry(auto_describe=False)
    server = start_metrics_server(sock_path, registry=coll)
    try:
        # bind succeeded; the file is now an actual UDS socket, not the
        # stale empty file we created above.
        assert stat.S_ISSOCK(sock_path.stat().st_mode)
    finally:
        _close_server(server)


def test_scrape_returns_prom_text(tmp_path: Path) -> None:
    """End-to-end scrape: HTTP/1.0 GET /metrics over AF_UNIX returns Prom text."""
    sock_path = tmp_path / "metrics.sock"
    coll = CollectorRegistry(auto_describe=False)
    # Register a known counter so the scrape body is non-empty.
    counter = Counter(
        "scrape_test_total",
        "Counter for the scrape test.",
        ["kind"],
        registry=coll,
    )
    counter.labels(kind="probe").inc(7)

    server = start_metrics_server(sock_path, registry=coll)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(sock_path))
        try:
            request = (
                b"GET /metrics HTTP/1.0\r\n"
                b"Host: localhost\r\n"
                b"User-Agent: test-scrape\r\n"
                b"Connection: close\r\n"
                b"\r\n"
            )
            client.sendall(request)
            chunks: list[bytes] = []
            while True:
                buf = client.recv(4096)
                if not buf:
                    break
                chunks.append(buf)
            response = b"".join(chunks)
        finally:
            client.close()

        assert response.startswith(b"HTTP/1."), response[:64]
        assert b" 200 " in response.split(b"\r\n", 1)[0], response[:64]
        assert b"# HELP scrape_test_total" in response
        assert b'scrape_test_total{kind="probe"}' in response or (
            b"scrape_test_total_total" in response
        )
    finally:
        _close_server(server)
        thread.join(timeout=2.0)


def test_start_metrics_server_creates_parent_directory(tmp_path: Path) -> None:
    """start_metrics_server creates missing parent directories.

    On the box the daemon expects ``/run/spark-modem-watchdog/`` to
    exist; the helper does ``mkdir(parents=True, exist_ok=True)`` so
    a fresh boot doesn't crash on missing ``/run/.../`` subdir.
    """
    sock_path = tmp_path / "nested" / "subdir" / "metrics.sock"
    assert not sock_path.parent.exists()
    coll = CollectorRegistry(auto_describe=False)

    server = start_metrics_server(sock_path, registry=coll)
    try:
        assert sock_path.parent.exists()
        assert sock_path.exists()
    finally:
        _close_server(server)
