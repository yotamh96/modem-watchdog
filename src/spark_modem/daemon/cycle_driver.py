"""Cycle driver — observe → policy → actions → persist → status → webhook.

Single-cycle pipeline (RECOVERY_SPEC §8 ordering enforced inside
``policy.engine.run_cycle``; the driver respects the result by atomically
persisting per-modem states + globals after dispatching actions).

NFR-11: a deliberately-thrown policy exception is caught, logged, and
the cycle continues; ``status.json`` is still written with whatever
snapshots succeeded.

SC #5: the driver constructs and enqueues the four canonical webhook
envelopes (``HealthyToDegraded``, ``RecoveringToExhausted``,
``ActionFailedWebhook``).  ``DaemonRestart`` is emitted ONCE at boot from
``daemon/main.py`` — not a per-cycle concern.

Plan 03-07 / E-04: SIM-swap detection runs AFTER observation and BEFORE
``policy.engine.run_cycle`` so the engine reads post-reset ModemState (the
detection pipeline calls ``StateStore.reset_modem_streak_and_counters`` for
each swapped usb_path; otherwise the engine would emit a state transition
based on stale streak/counters).  ICCID values are sha256[:8]-redacted in the
emitted ``SimSwapped`` event payload — daemon never logs raw ICCIDs (Issue
#8 / T-03-07-02).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from spark_modem.actions.context import ActionContext
from spark_modem.actions.dispatcher import execute_and_verify, is_registered
from spark_modem.actions.result import ActionResult
from spark_modem.config.settings import Settings
from spark_modem.inventory.descriptor import ModemDescriptor
from spark_modem.observer.diag_builder import build_diag
from spark_modem.observer.orchestrator import observe_all
from spark_modem.policy import engine as policy_engine
from spark_modem.policy.context import PolicyContext
from spark_modem.policy.result import CycleResult
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.state_store.store import StateStore
from spark_modem.status_reporter.status import write_status_json
from spark_modem.subproc.result import CompletedProcess
from spark_modem.wire.carriers import CarrierTable
from spark_modem.wire.diag import Diag, ModemSnapshot, WhoModem
from spark_modem.wire.enums import ActionKind
from spark_modem.wire.enums import ActionResult as ActionResultEnum
from spark_modem.wire.events import Event, SimSwapped
from spark_modem.wire.events import StateTransition as StateTransitionEvent
from spark_modem.wire.globals import GlobalsState
from spark_modem.wire.identity import Identity
from spark_modem.wire.state import ModemState, state_to_int
from spark_modem.wire.status import (
    StatusCycleSummary,
    StatusModemSummary,
    StatusPerModem,
    StatusReport,
)
from spark_modem.wire.webhook import (
    ActionFailedWebhook,
    HealthyToDegraded,
    RecoveringToExhausted,
    WebhookEnvelope,
)
from spark_modem.zao_log.protocol import ZaoLogTailer
from spark_modem.zao_log.snapshot import ZaoSnapshot

logger = logging.getLogger(__name__)


class ClockProto(Protocol):
    """Monotonic + wall-clock surface (ADR-0007)."""

    def monotonic(self) -> float: ...
    def wall_clock_iso(self) -> str: ...


class SubprocRunnerProto(Protocol):
    """SubprocRunner surface (matches ``spark_modem.subproc.runner.run``).

    Both production module-level ``run`` (when wrapped) and the
    ``FakeRunner`` test fake satisfy this Protocol — the cycle driver
    never sees the difference.
    """

    async def run(
        self,
        argv: list[str],
        *,
        timeout_s: float,
        stdin: bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> CompletedProcess: ...


class InventorySourceProto(Protocol):
    """``async scan() -> list[ModemDescriptor]`` — production ``SysfsInventory``
    and ``FixtureInventory`` both satisfy this."""

    async def scan(self) -> list[ModemDescriptor]: ...


class EventLogWriterProto(Protocol):
    """Append-only events.jsonl writer surface."""

    def append(self, event: Event) -> None: ...


class MetricRegistryProto(Protocol):
    """Subset of ``MetricRegistry`` consumed by the cycle driver."""

    def record_action(
        self,
        kind: ActionKind,
        modem: str,
        result: ActionResultEnum,
    ) -> None: ...

    def observe_cycle_duration(self, seconds: float) -> None: ...
    def set_modem_state(self, modem: str, value: int) -> None: ...
    def set_cycle_drift(self, seconds: float) -> None: ...


class WebhookPosterProto(Protocol):
    """``async enqueue(envelope)`` — production ``WebhookPoster`` and
    ``FakeWebhookPoster`` test fake both satisfy this."""

    async def enqueue(self, envelope: WebhookEnvelope) -> None: ...


@dataclass(frozen=True)
class RunCycleResult:
    """One cycle's full output — return value of ``run_one_cycle``."""

    diag: Diag
    cycle_result: CycleResult | None
    action_results: list[ActionResult] = field(default_factory=list)
    policy_exception: str | None = None


class CycleDriver:
    """Wires every Phase 2 subsystem into a single per-cycle pipeline."""

    def __init__(
        self,
        *,
        store: StateStore,
        settings: Settings,
        clock: ClockProto,
        runner: SubprocRunnerProto,
        inventory: InventorySourceProto,
        zao: ZaoLogTailer,
        carrier_table: CarrierTable,
        event_logger: EventLogWriterProto,
        metrics: MetricRegistryProto,
        webhook_poster: WebhookPosterProto | None = None,
    ) -> None:
        self._store = store
        self._settings = settings
        self._clock = clock
        self._runner = runner
        self._inventory = inventory
        self._zao = zao
        self._carriers = carrier_table
        self._events = event_logger
        self._metrics = metrics
        self._webhook = webhook_poster

    async def run_one_cycle(self, *, cycle_id: int) -> RunCycleResult:
        """observe → policy → actions → persist → status → webhook."""
        cycle_start_mono = self._clock.monotonic()

        # 1. Inventory + observe (NFR-11: errors are data; never crash cycle)
        modems = await self._inventory.scan()

        def qmi_factory(m: ModemDescriptor) -> QmiWrapper:
            # E-05: pass descriptor.ns so QmiWrapper auto-prepends `ip netns
            # exec <ns>` when running in a per-line netns; None on bench
            # Jetson is a no-op (PITFALLS §6.2 — never setns from asyncio).
            return QmiWrapper(runner=self._runner, device=f"/dev/{m.cdc_wdm}", ns=m.ns)

        try:
            snapshots: list[ModemSnapshot] = await observe_all(
                modems,
                qmi_factory,
                self._zao,
                self._clock,
            )
        except Exception:
            logger.exception("observe_all crashed; continuing with empty snapshots")
            snapshots = []

        zao_snap = (
            self._zao.snapshot()
            if hasattr(self._zao, "snapshot")
            else ZaoSnapshot.unknown(reason="no_snapshot")
        )
        diag = build_diag(snapshots, zao_snap, cycle_id, self._clock)

        # 1b. E-04 SIM-swap detection (FR-4: latency = one cycle).
        #     Runs AFTER snapshots collection AND BEFORE policy.engine.run_cycle
        #     because the engine reads ModemState which depends on streak +
        #     counters being correct for THIS cycle's decision.  Per-modem
        #     ICCID was extracted by the observer's uim-get-card-status parse
        #     (Phase 2 issue_extractor; Plan 03-07 wires it through
        #     ModemSnapshot.identity_iccid).  Cycle driver loads the identity
        #     map ONCE per cycle, compares, and on diff: persists the new
        #     identity AND resets streak + counters atomically (RECOVERY_SPEC §8
        #     single-write discipline preserved by
        #     StateStore.reset_modem_streak_and_counters).  Then emits a
        #     STRUCTURED SimSwapped event with sha256[:8]-redacted ICCIDs
        #     (Issue #8: NEVER logger.info; T-03-07-02 raw-ICCID prohibition).
        await self._detect_and_handle_sim_swaps(modems, snapshots)

        # 2. Hydrate prior states for the modems we observed
        prior_states: dict[str, ModemState] = {}
        for m in modems:
            load = await self._store.load_modem_state(m.usb_path)
            prior_states[m.usb_path] = load.state

        globals_load = await self._store.load_globals()
        globals_state: GlobalsState = globals_load.state

        # 3. Policy (NFR-11: catch, log, continue with empty plans).
        ctx = PolicyContext(
            clock=self._clock,
            config=self._settings,
            maintenance_active=(
                globals_state.maintenance is not None and globals_state.maintenance.active
            ),
            expected_modem_count=len(modems) or 4,
        )
        cycle_result: CycleResult | None = None
        policy_exception: str | None = None
        try:
            cycle_result = policy_engine.run_cycle(
                diag,
                prior_states,
                globals_state,
                ctx,
            )
        except Exception as exc:  # NFR-11
            logger.exception(
                "policy.run_cycle raised — cycle continues with empty plans",
            )
            policy_exception = repr(exc)

        # 4. Dispatch actions (cheap only in Phase 2; destructive land Phase 4).
        action_results: list[ActionResult] = []
        if cycle_result is not None:
            action_results = await self._dispatch_actions(cycle_result, modems)

        # 5. Persist new states + globals atomically (one write per modem).
        if cycle_result is not None:
            await self._persist_states_and_globals(
                cycle_result,
                action_results,
                globals_state,
            )

        # 6. status.json + per-cycle metrics.
        cycle_duration = self._clock.monotonic() - cycle_start_mono
        self._metrics.observe_cycle_duration(cycle_duration)
        states_for_status: dict[str, ModemState] = (
            cycle_result.new_states if cycle_result is not None else prior_states
        )
        self._write_status_report(
            cycle_id=cycle_id,
            cycle_duration=cycle_duration,
            modems=modems,
            states=states_for_status,
            actions_executed=len(action_results),
            transitions=(len(cycle_result.transitions) if cycle_result is not None else 0),
            maintenance=globals_state.maintenance,
        )
        for usb_path, st in states_for_status.items():
            self._metrics.set_modem_state(usb_path, state_to_int(st))

        # 7. Webhook enqueue for transitions (cycle never blocks on send).
        if self._webhook is not None and cycle_result is not None:
            await self._enqueue_webhooks(cycle_result, action_results)

        return RunCycleResult(
            diag=diag,
            cycle_result=cycle_result,
            action_results=action_results,
            policy_exception=policy_exception,
        )

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    async def _detect_and_handle_sim_swaps(
        self,
        modems: list[ModemDescriptor],
        snapshots: list[ModemSnapshot],
    ) -> None:
        """Plan 03-07 / E-04: detect ICCID changes; reset + emit SimSwapped.

        Atomic ordering (RECOVERY_SPEC §8 spirit; T-03-07-03 mitigation):
          1. Persist updated identity map (save_identity_map) — atomic;
             takes globals_lock + state-store flock.
          2. For each swapped usb_path: reset_modem_streak_and_counters —
             atomic single write per RECOVERY_SPEC §8; takes per-modem
             asyncio.Lock + flock.
          3. Emit structured SimSwapped event via event_logger.append with
             sha256[:8]-redacted ICCIDs (NEVER logger.info — Issue #8).

        New-modem path (no prior identity for usb_path): identity persisted
        but NO reset and NO SimSwapped event — this is enrollment, not swap.
        """
        prior_identities = await self._store.load_identity_map()

        # Build the current identity map only for modems whose snapshot
        # surfaced an ICCID (transient absence is NOT a swap signal — the
        # observer's empty-string-collapses-to-None contract handles this).
        current_identities: dict[str, Identity] = {}
        ts = self._clock.wall_clock_iso()
        for desc, snap in zip(modems, snapshots, strict=True):
            if snap.identity_iccid is None or snap.identity_imsi is None:
                continue
            prior_id = prior_identities.get(desc.usb_path)
            first_seen = prior_id.first_seen_iso if prior_id is not None else ts
            current_identities[desc.usb_path] = Identity(
                usb_path=desc.usb_path,
                iccid=snap.identity_iccid,
                imsi=snap.identity_imsi,
                first_seen_iso=first_seen,
                last_seen_iso=ts,
            )

        # Compute swap targets BEFORE persisting the new identity map so
        # the comparison reflects the prior-vs-current diff exactly.
        sim_swap_targets: list[tuple[str, str, str]] = []  # (usb_path, old, new)
        for usb_path, current_id in current_identities.items():
            prior_id = prior_identities.get(usb_path)
            if prior_id is not None and prior_id.iccid != current_id.iccid:
                sim_swap_targets.append(
                    (usb_path, prior_id.iccid, current_id.iccid),
                )

        # Persist the updated identity map iff anything changed: this covers
        # both swap targets AND new-modem additions (where prior_id is None).
        identity_map_changed = sim_swap_targets or any(
            usb_path not in prior_identities
            or prior_identities[usb_path].iccid != current_id.iccid
            or prior_identities[usb_path].imsi != current_id.imsi
            for usb_path, current_id in current_identities.items()
        )
        if identity_map_changed:
            await self._store.save_identity_map(current_identities)

        # Reset streak + counters atomically for each swapped modem; emit
        # SimSwapped via event_logger.append AFTER the reset so events.jsonl
        # is a chronological projection of post-reset state.
        for usb_path, old_iccid, new_iccid in sim_swap_targets:
            await self._store.reset_modem_streak_and_counters(usb_path)
            old_hash = hashlib.sha256(old_iccid.encode("utf-8")).hexdigest()[:8]
            new_hash = hashlib.sha256(new_iccid.encode("utf-8")).hexdigest()[:8]
            self._events.append(
                SimSwapped(
                    ts_iso=ts,
                    usb_path=usb_path,
                    iccid_hash_old=old_hash,
                    iccid_hash_new=new_hash,
                ),
            )

    async def _dispatch_actions(
        self,
        cycle_result: CycleResult,
        modems: list[ModemDescriptor],
    ) -> list[ActionResult]:
        """Execute each non-suppressed PlannedAction whose kind is registered."""
        out: list[ActionResult] = []
        cdc_by_usb: dict[str, str] = {m.usb_path: m.cdc_wdm for m in modems}
        # E-05: descriptor.ns flows into the per-action QmiWrapper so that
        # `ip netns exec <ns>` is prepended when the modem lives in a netns.
        ns_by_usb: dict[str, str | None] = {m.usb_path: m.ns for m in modems}

        for plan in cycle_result.plans:
            if not is_registered(plan.kind):
                # Phase 4 destructive actions are not yet registered;
                # the policy engine still emits them so the replay
                # harness can classify them.
                continue
            if (
                plan.suppressed_by_backoff
                or plan.suppressed_by_signal_gate
                or plan.suppressed_by_dry_run
            ):
                continue
            if plan.reason.startswith("skip:"):
                continue

            who = plan.who
            if not isinstance(who, WhoModem):
                # WhoHost (driver_reset) — Phase 4 wires this; no per-modem device.
                continue

            cdc = cdc_by_usb.get(who.usb_path)
            if cdc is None:
                # No descriptor for this usb_path (modem disappeared between
                # observe and dispatch).  Skip; next cycle will re-evaluate.
                continue
            ns_for_action = ns_by_usb.get(who.usb_path)

            per_action_qmi = QmiWrapper(
                runner=self._runner,
                device=f"/dev/{cdc}",
                ns=ns_for_action,  # E-05; None on single-namespace bench Jetson
            )
            per_action_ctx = ActionContext(
                qmi=per_action_qmi,
                clock=self._clock,
                config=self._settings,
                carrier_table=self._carriers,
                event_logger=self._events,
            )
            result = await execute_and_verify(
                plan.kind,
                who,
                per_action_ctx,
                dry_run=self._settings.dry_run,
            )
            out.append(result)
            self._metrics.record_action(
                plan.kind,
                who.usb_path,
                ActionResultEnum.SUCCESS if result.succeeded else ActionResultEnum.FAILURE,
            )

        return out

    async def _persist_states_and_globals(
        self,
        cycle_result: CycleResult,
        action_results: list[ActionResult],
        prior_globals: GlobalsState,
    ) -> None:
        """Write per-modem states atomically; emit StateTransition events."""
        for usb_path, new_state in cycle_result.new_states.items():
            last_action_mono: float | None = new_state.last_action_monotonic
            for ar in action_results:
                if isinstance(ar.who, WhoModem) and ar.who.usb_path == usb_path:
                    last_action_mono = self._clock.monotonic()
            state_to_persist = new_state.model_copy(
                update={
                    "last_action_monotonic": last_action_mono,
                    "last_state_transition_iso": self._clock.wall_clock_iso(),
                },
            )
            await self._store.save_modem_state(usb_path, state_to_persist)

        if cycle_result.new_globals != prior_globals:
            await self._store.save_globals(cycle_result.new_globals)

        # Log every transition to events.jsonl (NFR-20).
        for tr in cycle_result.transitions:
            self._events.append(
                StateTransitionEvent(
                    ts_iso=self._clock.wall_clock_iso(),
                    usb_path=tr.usb_path,
                    from_state=tr.from_state,
                    to_state=tr.to_state,
                    cause=tr.cause,
                    action=None,
                    dry_run=self._settings.dry_run,
                ),
            )

        # Plan 04-05 / B-04: ActionSkipped events emitted alongside the
        # legacy PlannedAction.suppressed_* flags. Order: state writes
        # FIRST (above), event-log appends SECOND -- if the daemon crashes
        # between, a re-run reads the pre-action state and re-derives the
        # gate decisions; events.jsonl is advisory, ModemState is
        # authoritative (RECOVERY_SPEC §8 atomic-write ordering).
        for skipped in cycle_result.skipped:
            self._events.append(skipped)

    async def _enqueue_webhooks(
        self,
        cycle_result: CycleResult,
        action_results: list[ActionResult],
    ) -> None:
        """SC #5: construct + enqueue HealthyToDegraded / RecoveringToExhausted /
        ActionFailedWebhook envelopes.

        ``DaemonRestart`` is the daemon-main's responsibility — emitted
        ONCE at boot, not per cycle.
        """
        assert self._webhook is not None  # narrowed by caller
        ts = self._clock.wall_clock_iso()

        # 7a. State-transition envelopes.
        for tr in cycle_result.transitions:
            if tr.from_state == "healthy" and tr.to_state == "degraded":
                env = WebhookEnvelope(
                    payload=HealthyToDegraded(
                        ts_iso=ts,
                        modem_usb_path=tr.usb_path,
                        prior_state=tr.from_state,
                        new_state=tr.to_state,
                        reason=tr.cause,
                    ),
                )
                await self._webhook.enqueue(env)
            elif tr.from_state.startswith("recovering") and tr.to_state == "exhausted":
                # Phase 2 has no destructive actions registered, so the
                # action_chain stand-in lists any cheap actions dispatched
                # for this modem this cycle.  Phase 4 records the real
                # destructive ladder.
                chain = [
                    ar.kind
                    for ar in action_results
                    if isinstance(ar.who, WhoModem) and ar.who.usb_path == tr.usb_path
                ]
                env = WebhookEnvelope(
                    payload=RecoveringToExhausted(
                        ts_iso=ts,
                        modem_usb_path=tr.usb_path,
                        action_chain=chain,
                        exhaustion_reason=tr.cause,
                    ),
                )
                await self._webhook.enqueue(env)

        # 7b. Action-failed envelopes.
        for ar in action_results:
            if ar.succeeded:
                continue
            usb = ar.who.usb_path if isinstance(ar.who, WhoModem) else ""
            env = WebhookEnvelope(
                payload=ActionFailedWebhook(
                    ts_iso=ts,
                    modem_usb_path=usb,
                    action=ar.kind,
                    failure_reason=ar.failure_reason or "unknown",
                ),
            )
            await self._webhook.enqueue(env)

    def _write_status_report(
        self,
        *,
        cycle_id: int,
        cycle_duration: float,
        modems: list[ModemDescriptor],
        states: dict[str, ModemState],
        actions_executed: int,
        transitions: int,
        maintenance: object,
    ) -> None:
        """Build and atomically write status.json (FR-41 / O-01)."""
        # Aggregate counts.
        healthy = degraded = recovering = exhausted = unknown = 0
        rf_blocked = 0
        per_modem: list[StatusPerModem] = []

        for m in modems:
            st = states.get(m.usb_path)
            if st is None:
                unknown += 1
                per_modem.append(
                    StatusPerModem(
                        usb_path=m.usb_path,
                        cdc_wdm=m.cdc_wdm,
                        line=m.line,
                        state="unknown",
                        state_int=0,
                        rf_blocked=False,
                    ),
                )
                continue

            state_name = st.state
            if state_name == "healthy":
                healthy += 1
            elif state_name == "degraded":
                degraded += 1
            elif state_name == "recovering":
                recovering += 1
            elif state_name == "exhausted":
                exhausted += 1
            else:
                unknown += 1
            if st.rf_blocked:
                rf_blocked += 1

            per_modem.append(
                StatusPerModem(
                    usb_path=m.usb_path,
                    cdc_wdm=m.cdc_wdm,
                    line=m.line,
                    state=state_name,
                    state_int=state_to_int(st),
                    rf_blocked=st.rf_blocked,
                ),
            )

        summary = StatusModemSummary(
            expected_modems=len(modems),
            healthy=healthy,
            degraded=degraded,
            recovering=recovering,
            rf_blocked=rf_blocked,
            exhausted=exhausted,
            unknown=unknown,
        )

        # maintenance_active_until_iso — only when MaintenanceWindow is active.
        maintenance_until: str | None = None
        if maintenance is not None and getattr(maintenance, "active", False):
            maintenance_until = getattr(maintenance, "expires_iso", None)

        report = StatusReport(
            last_modified=self._clock.wall_clock_iso(),
            cycle_index=cycle_id,
            cycle=StatusCycleSummary(
                n=cycle_id,
                duration_seconds=max(0.0, cycle_duration),
                next_at_iso=None,
            ),
            summary=summary,
            modems=per_modem,
            cycle_actions_executed=actions_executed,
            cycle_transitions=transitions,
            carrier_table_sha256="",
            maintenance_active_until_iso=maintenance_until,
        )
        status_path = Path(self._settings.state_root) / "status.json"
        write_status_json(status_path, report)
