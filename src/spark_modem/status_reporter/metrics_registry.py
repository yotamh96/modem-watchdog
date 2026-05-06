"""Typed metric registry — single chokepoint for every Prom metric we set/inc.

Cardinality discipline (ADR-0013):
  - ``modem_state_value{modem}`` is a SINGLE Gauge whose VALUE is the
    integer state code (0..4 stable mapping per ``state_to_int``). NOT
    one-hot. The label set is just ``{modem}``; ``state`` does NOT
    appear as a label on this gauge. CLAUDE.md anti-pattern: ``state``
    as a one-hot Prometheus label.
  - ``state_duration_seconds{modem, state}`` is the EXCEPTION (per
    ADR-0013 §"Exception"): histograms inherently multiplex per-bucket
    series, and time-in-state is a measurement dimension not a current-
    state indicator. Bucket array is ``[1, 5, 15, 60, 300, 1800, 7200,
    86400]`` (O-02), bounded.
  - ``webhook_delivery_total{result}`` (O-04) — closed enum
    ``{sent, failed, dropped, coalesced, skipped_no_url, skipped_no_dns}``.

Bucket selections (Claude's Discretion):
  - ``cycle_duration_seconds`` buckets ``(0.5, 1, 2, 4, 8, 16, 32)`` —
    targets M5's 10 s P99 budget with two-sided visibility (catches
    sub-second outliers AND budget breaches before P99 alerts fire).

Phase 2 supports a Windows-friendly mode: when ``prometheus_client`` is
installed but the AF_UNIX server cannot start (Win10 < 1803 or wsgiref
quirks), the registry still records — there is just no scrape endpoint.
Tests assert metric updates via ``prometheus_client.REGISTRY.collect()``.

The ``prometheus_client`` ``REGISTRY`` is a process-global singleton;
constructing two ``MetricRegistry`` instances in the same process raises
``ValueError`` on duplicate metric registration. Tests use a fixture
that snapshots collectors and unregisters them in teardown.
"""

from __future__ import annotations

from prometheus_client import REGISTRY, Counter, Gauge, Histogram
from prometheus_client.metrics import MetricWrapperBase
from prometheus_client.registry import CollectorRegistry

from spark_modem.wire.enums import ActionKind, ActionResult

# Cycle duration buckets — claude discretion, M5 ≤10 s P99 budget.
_CYCLE_BUCKETS: tuple[float, ...] = (0.5, 1, 2, 4, 8, 16, 32)

# state_duration histogram buckets — O-02 mandates exactly this array.
# Targets MTTR semantics: 1 s (cheap), 5 s (SIM cycle), 15 s (modem
# reset), 60 s (M2 SIM target), 300 s (5 min), 1800 s (30 min), 7200 s
# (2 h), 86400 s (24 h — stuck-unhealthy detection). +Inf is implicit.
_STATE_DURATION_BUCKETS: tuple[float, ...] = (1, 5, 15, 60, 300, 1800, 7200, 86400)

_METRIC_NAMES: tuple[str, ...] = (
    "actions_total",
    "signal_rsrp_dbm",
    "signal_rsrq_db",
    "signal_snr_db",
    "cycle_duration_seconds",
    "modem_state_value",
    "state_duration_seconds",
    "cycle_drift_seconds",
    "webhook_delivery_total",
    "daemon_self_health",
)


class MetricRegistry:
    """Single-instance per process. Cycle driver constructs once at startup.

    Every set/inc on a Prom metric MUST go through a typed accessor on
    this class — that gives us a code-review chokepoint to enforce
    ADR-0013 / O-02..O-04 discipline.
    """

    def __init__(self, *, registry: CollectorRegistry | None = None) -> None:
        # Allow tests (and a future hot-reload path) to inject an
        # isolated CollectorRegistry; production passes None and uses
        # the global REGISTRY for scrape exposure.
        reg = registry if registry is not None else REGISTRY

        self._actions_total = Counter(
            "actions_total",
            "Recovery actions executed by kind, modem, and result.",
            ["kind", "modem", "result"],
            registry=reg,
        )
        self._signal_rsrp_dbm = Gauge(
            "signal_rsrp_dbm",
            "RSRP in dBm per modem.",
            ["modem"],
            registry=reg,
        )
        self._signal_rsrq_db = Gauge(
            "signal_rsrq_db",
            "RSRQ in dB per modem.",
            ["modem"],
            registry=reg,
        )
        self._signal_snr_db = Gauge(
            "signal_snr_db",
            "SNR in dB per modem.",
            ["modem"],
            registry=reg,
        )
        self._cycle_duration_seconds = Histogram(
            "cycle_duration_seconds",
            "Wall-clock duration of each cycle in seconds.",
            buckets=_CYCLE_BUCKETS,
            registry=reg,
        )
        self._modem_state_value = Gauge(
            "modem_state_value",
            (
                "Per-modem state encoded as integer (ADR-0013): "
                "0=unknown, 1=healthy, 2=degraded, 3=recovering, 4=exhausted."
            ),
            ["modem"],
            registry=reg,
        )
        self._state_duration_seconds = Histogram(
            "state_duration_seconds",
            "Time spent in each state per modem (seconds).",
            ["modem", "state"],
            buckets=_STATE_DURATION_BUCKETS,
            registry=reg,
        )
        self._cycle_drift_seconds = Gauge(
            "cycle_drift_seconds",
            ("Signed gauge: now_monotonic - expected_next_cycle_monotonic, clamped to >=0 (O-03)."),
            registry=reg,
        )
        self._webhook_delivery_total = Counter(
            "webhook_delivery_total",
            (
                "Webhook deliveries by result "
                "(sent / failed / dropped / coalesced / skipped_no_url / skipped_no_dns)."
            ),
            ["result"],
            registry=reg,
        )
        self._daemon_self_health = Counter(
            "daemon_self_health",
            "Daemon self-health events. kind values: rss (psutil tripwire).",
            ["kind"],
            registry=reg,
        )

    # ------------------------------------------------------------------
    # recording API — typed wrappers; cycle driver / webhook poster /
    # actions dispatcher / cycle scheduler call exactly these.
    # ------------------------------------------------------------------

    def record_action(
        self,
        kind: ActionKind,
        modem: str,
        result: ActionResult,
    ) -> None:
        """Increment ``actions_total{kind, modem, result}`` (NFR-21)."""
        self._actions_total.labels(
            kind=kind.value,
            modem=modem,
            result=result.value,
        ).inc()

    def record_signal(
        self,
        modem: str,
        *,
        rsrp: int | None,
        rsrq: float | None,
        snr: float | None,
    ) -> None:
        """Set per-modem signal gauges. Missing values are skipped."""
        if rsrp is not None:
            self._signal_rsrp_dbm.labels(modem=modem).set(float(rsrp))
        if rsrq is not None:
            self._signal_rsrq_db.labels(modem=modem).set(float(rsrq))
        if snr is not None:
            self._signal_snr_db.labels(modem=modem).set(float(snr))

    def observe_cycle_duration(self, seconds: float) -> None:
        """Observe a single cycle's wall-clock duration (M5 ≤10 s P99)."""
        self._cycle_duration_seconds.observe(max(0.0, seconds))

    def set_modem_state(self, modem: str, value: int) -> None:
        """ADR-0013 integer encoding. Caller passes ``state_to_int(state)``.

        The label set is exactly ``{modem}`` — the integer state lives
        in the metric VALUE, not a ``state`` label. See
        ``CLAUDE.md`` anti-pattern catalogue and ADR-0013.
        """
        self._modem_state_value.labels(modem=modem).set(value)

    def observe_state_duration(
        self,
        modem: str,
        state: str,
        seconds: float,
    ) -> None:
        """Observe time-in-state. ``state`` IS a label here per ADR-0013 §exception."""
        self._state_duration_seconds.labels(modem=modem, state=state).observe(max(0.0, seconds))

    def set_cycle_drift(self, seconds: float) -> None:
        """O-03: clamp negative drift to 0 (monotonic regression is defensive-only)."""
        self._cycle_drift_seconds.set(max(0.0, seconds))

    def record_webhook_delivery(self, result: str) -> None:
        """Increment ``webhook_delivery_total{result}`` (O-04 enum)."""
        self._webhook_delivery_total.labels(result=result).inc()

    def record_rss_tripwire(self) -> None:
        """Phase 2 NFR-3: event-only.

        Phase 3's ``sd_notify`` watchdog reads
        ``daemon_self_health{kind="rss"}`` to decide whether to restart
        on RSS breach. Phase 2 just emits the counter + a paired event;
        no ``graceful_exit`` path here.
        """
        self._daemon_self_health.labels(kind="rss").inc()

    # ------------------------------------------------------------------
    # collectors — used by tests for unregister/teardown and by
    # diagnostics if we ever want a programmatic dump.
    # ------------------------------------------------------------------

    def iter_collectors(self) -> tuple[MetricWrapperBase, ...]:
        """Return the underlying prometheus_client metric objects.

        Order matches ``__init__`` registration order. Used by test
        teardown fixtures to ``REGISTRY.unregister(...)`` each one.
        """
        return (
            self._actions_total,
            self._signal_rsrp_dbm,
            self._signal_rsrq_db,
            self._signal_snr_db,
            self._cycle_duration_seconds,
            self._modem_state_value,
            self._state_duration_seconds,
            self._cycle_drift_seconds,
            self._webhook_delivery_total,
            self._daemon_self_health,
        )


def metric_names() -> tuple[str, ...]:
    """Snapshot of every metric name MetricRegistry registers.

    Public for tests and for diagnostic tooling that wants to assert
    the surface without instantiating MetricRegistry.
    """
    return _METRIC_NAMES
