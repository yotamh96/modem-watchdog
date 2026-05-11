"""QmiWrapper -- the only place outside src/spark_modem/subproc/ that
invokes qmicli.

Every qmicli method goes through `subproc.runner.run` (the wrapper does not
spawn processes itself); SP-04 lint enforces this. Every call unconditionally
includes `--device-open-proxy` (FR-74 / PITFALLS §1.5); direct-mode access
is never attempted. State-changing methods raise the in-critical-section
flag before calling the runner and clear it in a finally block (PITFALLS §1.4) so
the Phase 3 SIGTERM handler can wait for cleanup rather than cancelling
mid-call.

`classify()` maps a CompletedProcess to None (healthy) or a QmiError. The
PROXY_DIED short-circuit (PITFALLS §1.1) scans stderr for canonical libqmi
phrases that indicate the qmi-proxy went away; downstream policy/ uses this
to choose driver_reset rather than retrying (RECOVERY_SPEC §6.4 extension).
"""

from __future__ import annotations

from typing import Final, Protocol

from spark_modem.qmi.errors import QmiError, QmiErrorReason
from spark_modem.subproc.result import CompletedProcess

# PITFALLS §1.1 -- canonical libqmi phrases that mean the qmi-proxy is gone.
# Lowercased before match (stderr is normalized to lowercase before scan).
_PROXY_DIED_SIGNATURES: Final[tuple[bytes, ...]] = (
    b"proxy unavailable",
    b"couldn't open the qmi device: proxy unavailable",
    b"broken pipe",
    b"connection refused",
)

# Default per-call timeouts. Queries are cheap; state-changing calls
# (set_operating_mode, sim_power_on, modify_profile, set_ip_family) need
# longer because the modem actually mutates hardware state. Both values
# include subproc.runner's worst-case two-stage shutdown overhead.
_DEFAULT_TIMEOUT_S: Final[float] = 8.0
_STATE_CHANGE_TIMEOUT_S: Final[float] = 15.0

# Cap stderr captured into QmiError to bound memory (T-02-02-01).
_STDERR_EXCERPT_BYTES: Final[int] = 512


class SubprocRunner(Protocol):
    """The subset of `spark_modem.subproc.runner` that QmiWrapper depends on.

    Both the production runner module and tests/fakes/runner.FakeRunner
    satisfy this Protocol -- callers never see a difference at the type level.
    """

    async def run(
        self,
        argv: list[str],
        *,
        timeout_s: float,
        stdin: bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> CompletedProcess: ...


def _classify_completed_process(cp: CompletedProcess) -> QmiError | None:
    """Map a CompletedProcess to None (healthy) or a typed QmiError.

    Order is significant:
      1. Timeout wins -- a timed-out process may also have proxy-death
         residue in stderr, but the operationally-meaningful signal is
         that the call did not return in time.
      2. Proxy-died signature wins over generic NON_ZERO_EXIT so policy/
         can short-circuit to driver_reset.
      3. Generic non-zero exit otherwise.
      4. exit_code == 0 with no timeout returns None (healthy).
    """
    if cp.timed_out:
        return QmiError(
            reason=QmiErrorReason.TIMEOUT,
            argv=cp.argv,
            exit_code=cp.exit_code,
            stderr_excerpt=cp.stderr[:_STDERR_EXCERPT_BYTES].decode("utf-8", errors="replace"),
        )
    stderr_lower = cp.stderr.lower()
    for sig in _PROXY_DIED_SIGNATURES:
        if sig in stderr_lower:
            return QmiError(
                reason=QmiErrorReason.PROXY_DIED,
                argv=cp.argv,
                exit_code=cp.exit_code,
                stderr_excerpt=cp.stderr[:_STDERR_EXCERPT_BYTES].decode("utf-8", errors="replace"),
            )
    if not cp.succeeded:
        return QmiError(
            reason=QmiErrorReason.NON_ZERO_EXIT,
            argv=cp.argv,
            exit_code=cp.exit_code,
            stderr_excerpt=cp.stderr[:_STDERR_EXCERPT_BYTES].decode("utf-8", errors="replace"),
        )
    return None


class QmiWrapper:
    """Centralizes qmicli invocations behind a single class.

    Use case::

        wrapper = QmiWrapper(runner=spark_modem.subproc.runner, device="/dev/cdc-wdm0")
        cp = await wrapper.nas_get_signal_info()
        err = QmiWrapper.classify(cp)  # None on success, QmiError otherwise

    Phase 2 ships cheap query methods + cheap mutators (set_operating_mode,
    sim_power_on, modify_profile, set_ip_family). Destructive methods
    (modem_reset, usb_reset, driver_reset) land in Phase 4 with the
    signal-quality gate end-to-end.

    All methods unconditionally pass `--device-open-proxy` (FR-74). The
    `_in_critical_section` flag is set on every state-changing method
    (Phase 3 SIGTERM handler reads it).
    """

    def __init__(self, *, runner: SubprocRunner, device: str, ns: str | None = None) -> None:
        if not device:
            raise ValueError("QmiWrapper: device must be non-empty (e.g. '/dev/cdc-wdm0')")
        self._runner = runner
        self._device = device
        self._ns: str | None = ns
        self._in_critical_section: bool = False

    def _argv(self, qmicli_args: list[str]) -> list[str]:
        """Prepend ``ip netns exec <ns>`` to ``qmicli_args`` when self._ns is set (E-05).

        PITFALLS §6.2: NEVER setns() from the asyncio loop. The
        ``ip netns exec`` subprocess does its own setns in a forked
        child; the daemon's loop stays in the host namespace.

        Single source of truth — every qmicli method routes through
        this helper, so adding a Phase 4 destructive method without
        wrapping is caught by the parameterized regression test in
        ``tests/unit/qmi/test_wrapper_netns.py``.
        """
        if self._ns is None:
            return qmicli_args
        return ["ip", "netns", "exec", self._ns, *qmicli_args]

    # ---- query methods (read-only) -------------------------------------

    async def nas_get_signal_info(self) -> CompletedProcess:
        return await self._runner.run(
            self._argv(
                [
                    "qmicli",
                    "--device-open-proxy",
                    f"--device={self._device}",
                    "--nas-get-signal-info",
                ]
            ),
            timeout_s=_DEFAULT_TIMEOUT_S,
        )

    async def nas_get_serving_system(self) -> CompletedProcess:
        return await self._runner.run(
            self._argv(
                [
                    "qmicli",
                    "--device-open-proxy",
                    f"--device={self._device}",
                    "--nas-get-serving-system",
                ]
            ),
            timeout_s=_DEFAULT_TIMEOUT_S,
        )

    async def uim_get_card_status(self) -> CompletedProcess:
        return await self._runner.run(
            self._argv(
                [
                    "qmicli",
                    "--device-open-proxy",
                    f"--device={self._device}",
                    "--uim-get-card-status",
                ]
            ),
            timeout_s=_DEFAULT_TIMEOUT_S,
        )

    async def wds_get_packet_service_status(self) -> CompletedProcess:
        return await self._runner.run(
            self._argv(
                [
                    "qmicli",
                    "--device-open-proxy",
                    f"--device={self._device}",
                    "--wds-get-packet-service-status",
                ]
            ),
            timeout_s=_DEFAULT_TIMEOUT_S,
        )

    async def wds_get_profile_settings(self, *, profile_index: int = 1) -> CompletedProcess:
        return await self._runner.run(
            self._argv(
                [
                    "qmicli",
                    "--device-open-proxy",
                    f"--device={self._device}",
                    f"--wds-get-profile-settings=3gpp,{profile_index}",
                ]
            ),
            timeout_s=_DEFAULT_TIMEOUT_S,
        )

    async def wds_get_current_settings(self) -> CompletedProcess:
        return await self._runner.run(
            self._argv(
                [
                    "qmicli",
                    "--device-open-proxy",
                    f"--device={self._device}",
                    "--wds-get-current-settings",
                ]
            ),
            timeout_s=_DEFAULT_TIMEOUT_S,
        )

    async def dms_get_operating_mode(self) -> CompletedProcess:
        return await self._runner.run(
            self._argv(
                [
                    "qmicli",
                    "--device-open-proxy",
                    f"--device={self._device}",
                    "--dms-get-operating-mode",
                ]
            ),
            timeout_s=_DEFAULT_TIMEOUT_S,
        )

    async def dms_get_revision(self) -> CompletedProcess:
        """Read EM7421 firmware revision string (e.g. 'SWI9X30C_02.38.00.00').

        Read-only verb (does NOT set _in_critical_section); routes through
        subproc.runner (SP-04) and always passes --device-open-proxy (FR-74).
        Added in Phase 5 for fleet-fixture capture (X-02): downstream callers
        are `ctl capture-fleet-fixture` and `preflight_check_known_fleet_triple`.
        """
        return await self._runner.run(
            self._argv(
                [
                    "qmicli",
                    "--device-open-proxy",
                    f"--device={self._device}",
                    "--dms-get-revision",
                ]
            ),
            timeout_s=_DEFAULT_TIMEOUT_S,
        )

    # ---- state-changing methods (set _in_critical_section = True) ------

    async def dms_set_operating_mode(self, mode: str) -> CompletedProcess:
        """Mutates radio operating mode (online/low_power/persistent_low_power/...)."""
        self._in_critical_section = True
        try:
            return await self._runner.run(
                self._argv(
                    [
                        "qmicli",
                        "--device-open-proxy",
                        f"--device={self._device}",
                        f"--dms-set-operating-mode={mode}",
                    ]
                ),
                timeout_s=_STATE_CHANGE_TIMEOUT_S,
            )
        finally:
            self._in_critical_section = False

    async def uim_sim_power_on(self, *, slot: int = 1) -> CompletedProcess:
        """Re-energises the SIM application; recovers SIM_APP_DETECTED state."""
        self._in_critical_section = True
        try:
            return await self._runner.run(
                self._argv(
                    [
                        "qmicli",
                        "--device-open-proxy",
                        f"--device={self._device}",
                        f"--uim-sim-power-on={slot}",
                    ]
                ),
                timeout_s=_STATE_CHANGE_TIMEOUT_S,
            )
        finally:
            self._in_critical_section = False

    async def wds_modify_profile(
        self,
        *,
        profile_index: int,
        apn: str,
        ip_family: int = 4,
    ) -> CompletedProcess:
        """Programs the 3GPP profile APN. apn is passed as a single argv
        element after `apn=`; no separator injection is possible (T-02-02-02).
        """
        self._in_critical_section = True
        try:
            return await self._runner.run(
                self._argv(
                    [
                        "qmicli",
                        "--device-open-proxy",
                        f"--device={self._device}",
                        f"--wds-modify-profile=3gpp,{profile_index},apn={apn},ip-family={ip_family}",
                    ]
                ),
                timeout_s=_STATE_CHANGE_TIMEOUT_S,
            )
        finally:
            self._in_critical_section = False

    async def wds_set_ip_family(self, family: int) -> CompletedProcess:
        """Set raw-IP / IP family for the data path.

        family: 4 = IPv4, 6 = IPv6, 7 = IPv4+IPv6 (libqmi convention).

        Used by actions/fix_raw_ip.py -- exposing the call here keeps the
        typed boundary intact (no private-attribute access from actions/).
        """
        self._in_critical_section = True
        try:
            return await self._runner.run(
                self._argv(
                    [
                        "qmicli",
                        "--device-open-proxy",
                        f"--device={self._device}",
                        f"--wds-set-ip-family={family}",
                    ]
                ),
                timeout_s=_STATE_CHANGE_TIMEOUT_S,
            )
        finally:
            self._in_critical_section = False

    # ---- introspection -------------------------------------------------

    @property
    def in_critical_section(self) -> bool:
        return self._in_critical_section

    @property
    def device(self) -> str:
        return self._device

    @staticmethod
    def classify(cp: CompletedProcess) -> QmiError | None:
        """Returns None if cp is a healthy success, QmiError otherwise.

        Public for the observer/actions modules so they can branch on
        specific failure reasons (e.g. PROXY_DIED triggers driver_reset
        short-circuit per RECOVERY_SPEC §6.4 extension).
        """
        return _classify_completed_process(cp)
