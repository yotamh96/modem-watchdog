"""Tests for MetricRegistry — cross-platform.

Tests use a per-test isolated ``CollectorRegistry`` so the
process-global ``prometheus_client.REGISTRY`` is never touched. This
keeps the tests deterministic regardless of test execution order or
parallel pytest workers.
"""

from __future__ import annotations

import pytest
from prometheus_client.registry import CollectorRegistry

from spark_modem.status_reporter.metrics_registry import (
    MetricRegistry,
    metric_names,
)
from spark_modem.wire.enums import ActionKind, ActionResult


@pytest.fixture
def registry() -> tuple[MetricRegistry, CollectorRegistry]:
    """Fresh MetricRegistry backed by an isolated CollectorRegistry per test."""
    coll = CollectorRegistry(auto_describe=False)
    return MetricRegistry(registry=coll), coll


def _samples_for(coll: CollectorRegistry, metric_name: str) -> list[tuple[dict[str, str], float]]:
    """Collect ``(labels, value)`` tuples for every sample of ``metric_name``.

    ``prometheus_client`` strips the ``_total`` suffix from Counter
    family names (so a Counter registered as ``actions_total`` has
    ``family.name == "actions"`` but ``sample.name == "actions_total"``).
    We match on ``sample.name`` to handle both Gauge / Histogram
    (sample name == family name) and Counter (sample name has the
    ``_total`` suffix the caller actually registered) without special-
    casing.

    ``_created`` samples (per-process Counter creation timestamp) are
    skipped — tests assert counts, not creation times.
    """
    out: list[tuple[dict[str, str], float]] = []
    for family in coll.collect():
        # family.name is the de-suffixed name for Counters; we still
        # need to look at every family because prometheus_client tags
        # families by metric_type, not by sample-name suffix.
        for sample in family.samples:
            if sample.name.endswith("_created"):
                continue
            if sample.name == metric_name:
                out.append((dict(sample.labels), sample.value))
    return out


def test_metric_names_snapshot() -> None:
    """metric_names() exposes the entire NFR-21 + NFR-21.1 surface."""
    expected = {
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
    }
    assert set(metric_names()) == expected


def test_modem_state_value_is_single_gauge_not_one_hot(
    registry: tuple[MetricRegistry, CollectorRegistry],
) -> None:
    """ADR-0013: modem_state_value{modem} carries the integer state in its value.

    There is exactly ONE sample per modem; ``state`` does NOT appear as
    a label. Two modems → two samples. Cardinality stays bounded at
    ``|modems|`` series, regardless of state churn.
    """
    reg, coll = registry
    reg.set_modem_state("2-3.1.1", 3)  # recovering
    reg.set_modem_state("2-3.1.2", 1)  # healthy

    samples = _samples_for(coll, "modem_state_value")
    assert len(samples) == 2
    by_modem = {labels["modem"]: value for labels, value in samples}
    assert by_modem == {"2-3.1.1": 3.0, "2-3.1.2": 1.0}

    # No `state` label on any modem_state_value sample (anti-pattern guard).
    for labels, _ in samples:
        assert set(labels.keys()) == {"modem"}


def test_modem_state_value_value_changes_in_place_no_new_series(
    registry: tuple[MetricRegistry, CollectorRegistry],
) -> None:
    """A state transition mutates the existing gauge — does NOT create a new series."""
    reg, coll = registry
    reg.set_modem_state("2-3.1.1", 1)  # healthy
    reg.set_modem_state("2-3.1.1", 2)  # degraded
    reg.set_modem_state("2-3.1.1", 3)  # recovering

    samples = _samples_for(coll, "modem_state_value")
    assert len(samples) == 1
    labels, value = samples[0]
    assert labels == {"modem": "2-3.1.1"}
    assert value == 3.0


def test_state_duration_buckets_match_o_02(
    registry: tuple[MetricRegistry, CollectorRegistry],
) -> None:
    """O-02 mandates exactly [1, 5, 15, 60, 300, 1800, 7200, 86400].

    prometheus_client appends +Inf as the implicit final bucket. We
    assert the explicit edges match O-02 verbatim.
    """
    reg, coll = registry
    reg.observe_state_duration("2-3.1.1", "healthy", 30.0)

    bucket_edges: list[float] = []
    for family in coll.collect():
        if family.name != "state_duration_seconds":
            continue
        for sample in family.samples:
            if sample.name == "state_duration_seconds_bucket":
                le_str = sample.labels.get("le")
                if le_str is None:
                    continue
                # +Inf is implicit; ignore it for the explicit-edge check.
                if le_str == "+Inf":
                    continue
                bucket_edges.append(float(le_str))

    # bucket_edges has duplicates (one per labelset), so dedup + sort.
    expected = [1.0, 5.0, 15.0, 60.0, 300.0, 1800.0, 7200.0, 86400.0]
    assert sorted(set(bucket_edges)) == expected


def test_cycle_drift_clamps_to_zero_when_negative(
    registry: tuple[MetricRegistry, CollectorRegistry],
) -> None:
    """O-03: negative drift means monotonic regression — clamp to 0 (defensive)."""
    reg, coll = registry
    reg.set_cycle_drift(-5.0)

    samples = _samples_for(coll, "cycle_drift_seconds")
    assert len(samples) == 1
    _, value = samples[0]
    assert value == 0.0

    reg.set_cycle_drift(2.5)
    samples = _samples_for(coll, "cycle_drift_seconds")
    assert samples[0][1] == 2.5


def test_record_action_uses_kind_modem_result_labels(
    registry: tuple[MetricRegistry, CollectorRegistry],
) -> None:
    """actions_total{kind, modem, result} — verified label set + count."""
    reg, coll = registry
    reg.record_action(ActionKind.SOFT_RESET, "2-3.1.1", ActionResult.SUCCESS)
    reg.record_action(ActionKind.SOFT_RESET, "2-3.1.1", ActionResult.SUCCESS)
    reg.record_action(ActionKind.SET_APN, "2-3.1.2", ActionResult.FAILURE)

    # The Counter is registered as `actions_total`, so `_total_total`
    # is NOT how prometheus_client suffixes it — Counter.collect() emits
    # samples named `actions_total` directly when the registered name
    # already ends in `_total`.
    samples = _samples_for(coll, "actions_total")
    by_key = {(s[0]["kind"], s[0]["modem"], s[0]["result"]): s[1] for s in samples}

    assert by_key[("soft_reset", "2-3.1.1", "success")] == 2.0
    assert by_key[("set_apn", "2-3.1.2", "failure")] == 1.0


def test_record_signal_skips_none_values(
    registry: tuple[MetricRegistry, CollectorRegistry],
) -> None:
    """record_signal: None entries don't create samples."""
    reg, coll = registry
    reg.record_signal("2-3.1.1", rsrp=-95, rsrq=None, snr=12.5)

    rsrp_samples = _samples_for(coll, "signal_rsrp_dbm")
    rsrq_samples = _samples_for(coll, "signal_rsrq_db")
    snr_samples = _samples_for(coll, "signal_snr_db")

    assert len(rsrp_samples) == 1
    assert rsrp_samples[0][1] == -95.0
    assert len(rsrq_samples) == 0
    assert len(snr_samples) == 1
    assert snr_samples[0][1] == 12.5


def test_record_webhook_delivery_supports_o_04_enum(
    registry: tuple[MetricRegistry, CollectorRegistry],
) -> None:
    """O-04: each result enum value produces a separate label combination."""
    reg, coll = registry
    for result in (
        "sent",
        "failed",
        "dropped",
        "coalesced",
        "skipped_no_url",
        "skipped_no_dns",
    ):
        reg.record_webhook_delivery(result)

    samples = _samples_for(coll, "webhook_delivery_total")
    by_result = {labels["result"]: value for labels, value in samples}
    assert by_result == {
        "sent": 1.0,
        "failed": 1.0,
        "dropped": 1.0,
        "coalesced": 1.0,
        "skipped_no_url": 1.0,
        "skipped_no_dns": 1.0,
    }


def test_record_rss_tripwire_increments_self_health(
    registry: tuple[MetricRegistry, CollectorRegistry],
) -> None:
    """NFR-3: psutil tripwire increments daemon_self_health{kind="rss"}.

    Phase 2: event-only; Phase 3 sd_notify watchdog reads this counter
    to decide whether to restart. No graceful_exit hook here.
    """
    reg, coll = registry
    reg.record_rss_tripwire()
    reg.record_rss_tripwire()

    # Counters are exposed as `<name>_total` samples per OpenMetrics; the
    # registry name is `daemon_self_health` but the sample name is suffixed.
    samples = _samples_for(coll, "daemon_self_health_total")
    by_kind = {labels["kind"]: value for labels, value in samples}
    assert by_kind == {"rss": 2.0}


def test_observe_cycle_duration_clamps_negative_to_zero(
    registry: tuple[MetricRegistry, CollectorRegistry],
) -> None:
    """observe_cycle_duration: negative values clamp to 0 (defensive)."""
    reg, coll = registry
    reg.observe_cycle_duration(-1.0)

    # Histograms emit `<name>_sum` (sum of observations) and
    # `<name>_count`. The clamped observation contributes 0 to _sum and
    # 1 to _count.
    sum_samples = _samples_for(coll, "cycle_duration_seconds_sum")
    count_samples = _samples_for(coll, "cycle_duration_seconds_count")
    assert len(sum_samples) == 1
    assert sum_samples[0][1] == 0.0
    assert len(count_samples) == 1
    assert count_samples[0][1] == 1.0


def test_state_label_appears_only_on_state_duration_histogram(
    registry: tuple[MetricRegistry, CollectorRegistry],
) -> None:
    """ADR-0013: ``state`` label is permitted ONLY on state_duration_seconds.

    Verifies that no other metric in MetricRegistry exposes a ``state``
    label — guards against accidentally re-introducing the one-hot
    pattern on a gauge.
    """
    reg, coll = registry
    reg.set_modem_state("2-3.1.1", 3)
    reg.observe_cycle_duration(1.0)
    reg.set_cycle_drift(0.5)
    reg.record_action(ActionKind.SOFT_RESET, "2-3.1.1", ActionResult.SUCCESS)
    reg.observe_state_duration("2-3.1.1", "recovering", 10.0)

    for family in coll.collect():
        if family.name == "state_duration_seconds":
            continue
        for sample in family.samples:
            assert "state" not in sample.labels, (
                f"metric {family.name} sample {sample.name} has unexpected "
                f"`state` label — ADR-0013 forbids one-hot state encoding"
            )
