"""Prometheus UDS exporter — ``make_wsgi_app()`` over an AF_UNIX socket.

RESEARCH §2.6 verbatim shape:

  - ``_UnixWSGIServer`` subclasses ``UnixStreamServer + WSGIServer``.
    ``server_bind()`` does NOT call ``setsockopt(SO_REUSEADDR)`` — UDS
    kernels can return ``ENOPROTOOPT`` (Linux 5.10-tegra is in the known
    set). ``UnixStreamServer.server_bind`` is called directly, which
    skips the SO_REUSEADDR dance baked into ``WSGIServer.server_bind``.
  - ``setup_environ()`` is called after ``server_bind`` so wsgiref's
    ``SERVER_NAME`` etc. are present (values are nonsense on UDS but the
    WSGI handler does not actually consume them).
  - Stale socket file is removed via ``unlink(missing_ok=True)`` before
    bind (PITFALLS §13.3 — daemon restart after crash).
  - Socket mode is ``0o660`` so members of the ``adm`` group can scrape;
    non-adm users on the box cannot read metrics.
  - The server is run via ``asyncio.to_thread(serve_forever)`` by the
    caller — ``serve_forever`` is synchronous and would block the event
    loop otherwise. The dedicated thread is fine because scrapes are
    infrequent (~30 s) and sub-100 ms.

Windows note: ``socketserver.UnixStreamServer`` is POSIX-only (the
class is conditionally defined inside ``socketserver`` based on
``hasattr(socket, "AF_UNIX")`` at import time on the host's stdlib). On
Windows the module imports cleanly — ``_UnixWSGIServer`` is a stub
class that raises ``RuntimeError`` if instantiated, and
``start_metrics_server`` raises ``RuntimeError`` before any
POSIX-specific path is taken. Production target is Linux/aarch64; tests
mark the integration suite ``skipif(win32)``.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path
from typing import Final
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer

from prometheus_client import REGISTRY, make_wsgi_app
from prometheus_client.registry import CollectorRegistry

_SOCKET_MODE: Final[int] = 0o660


if sys.platform != "win32":
    # POSIX path — import the real UnixStreamServer and define the
    # functional MRO ``UnixStreamServer + WSGIServer``.
    from socketserver import UnixStreamServer

    class _UnixWSGIServer(UnixStreamServer, WSGIServer):
        """``WSGIServer`` over an AF_UNIX socket instead of TCP.

        The MRO is ``UnixStreamServer`` first so ``server_bind``
        resolves to its plain ``socket.bind(self.server_address)``
        rather than ``WSGIServer.server_bind`` (which calls
        ``setsockopt(SO_REUSEADDR)`` — invalid on UDS sockets on some
        kernels).
        """

        address_family = socket.AF_UNIX

        def server_bind(self) -> None:
            """Bind the AF_UNIX socket; populate ``environ`` for wsgiref."""
            # Plain UnixStreamServer bind — no SO_REUSEADDR setsockopt.
            UnixStreamServer.server_bind(self)
            # HTTPServer.server_bind would assign server_name/server_port
            # from self.server_address[:2]; AF_UNIX server_address is a
            # single path string with no (host, port) tuple, so we MUST
            # assign placeholders before setup_environ() reads them
            # (wsgiref/simple_server.py:56 unconditionally reads
            # self.server_name; missing attribute → AttributeError).
            # Values are nonsense for UDS but the WSGI handler does not
            # consume them; the scrape protocol uses the socket path only.
            self.server_name = "localhost"
            self.server_port = 0
            self.setup_environ()

else:  # pragma: no cover - Windows dev-host path

    class _UnixWSGIServer:  # type: ignore[no-redef]
        """Windows stub — raises if instantiated.

        ``socketserver.UnixStreamServer`` is POSIX-only (gated on
        ``hasattr(socket, "AF_UNIX")`` at the stdlib's import time).
        Tests skipif(win32); the production daemon never runs on
        Windows.
        """

        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError(
                "Prometheus UDS exporter requires AF_UNIX socket support; "
                "Windows dev hosts use FakeMetricsServer in tests."
            )


def start_metrics_server(
    socket_path: Path | str,
    *,
    registry: CollectorRegistry | None = None,
) -> _UnixWSGIServer:
    """Bind the AF_UNIX socket and return a server ready for ``serve_forever``.

    Caller wraps the returned server in
    ``asyncio.create_task(asyncio.to_thread(srv.serve_forever))``.

    Args:
      socket_path: Filesystem path the socket will be created at. Stale
        sockets from a previous run are removed before bind.
      registry: Optional ``CollectorRegistry``. Defaults to
        ``prometheus_client.REGISTRY`` so the daemon's MetricRegistry
        feeds straight into the scrape app.

    Raises:
      RuntimeError: When called on Windows (production target is Linux).
    """
    if sys.platform == "win32":
        # AF_UNIX exists on modern Windows but the wsgiref+to_thread
        # bridge is fragile and we have no production need for it.
        raise RuntimeError(
            "Prometheus UDS exporter requires AF_UNIX socket support; "
            "Windows dev hosts use FakeMetricsServer in tests."
        )

    target = Path(socket_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # PITFALLS §13.3: daemon restart after crash leaves a stale socket
    # file that would EADDRINUSE the bind. unlink() before bind is the
    # canonical fix; the daemon's PID lock (Phase 3) prevents a real
    # concurrent instance from racing here.
    target.unlink(missing_ok=True)

    reg = registry if registry is not None else REGISTRY
    server = _UnixWSGIServer(str(target), WSGIRequestHandler)
    server.set_app(make_wsgi_app(reg))
    target.chmod(_SOCKET_MODE)
    return server
