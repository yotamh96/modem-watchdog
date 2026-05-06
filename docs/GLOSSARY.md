# Glossary — spark-modem-watchdog v2

| Field         | Value                  |
| ------------- | ---------------------- |
| Status        | Draft                  |
| Owner         | TBD (modem platform)   |
| Last updated  | 2026-05-05             |

Terms a non-cellular engineer (or a future maintainer) needs to know
to read the rest of these docs. Defined here once; referenced from
elsewhere.

---

### APN — Access Point Name

The string the modem sends during PDP context activation that tells
the carrier "I want this kind of bearer." Example: `internetg`. Wrong
APN → no IP. Stored in the modem's profile #1 by `set_profile_wwan`.

### bonding

Combining multiple cellular uplinks into a single virtual link with
higher throughput / better resilience. Done here by Zao. The watchdog
does not implement bonding; it keeps the underlying lines healthy so
Zao can bond them.

### cdc-wdm

The kernel's character device for QMI control to a modem.
`/dev/cdc-wdm0` corresponds to the first qmi_wwan-managed device.
`qmicli -d /dev/cdc-wdm0 ...` opens it.

### cycle

One iteration of the daemon's main loop: observe → decide → act → persist.

### Diag

The typed JSON snapshot produced by the observer per cycle. Schema in
[SCHEMA.md § 2](SCHEMA.md#2-diag).

### dry-run

Plan actions but do not execute them. Used in dev, in shadow mode
during migration, and operator-driven for `spark-modem recovery
--dry-run`.

### ESN, MEID, IMEI

Modem identifiers. The daemon reads them but does not act on them
beyond logging. IMEI is the relevant one for LTE.

### exhausted

State for a modem whose recovery counters have hit all ceilings
without a fix. The daemon stops trying ladder rungs but keeps running
cheap actions (`set_apn`, `fix_raw_ip`). Counters decay back to zero
after K consecutive Healthy cycles.

### gates

Checks that may suppress a chosen action. See
[RECOVERY_SPEC.md § 6](RECOVERY_SPEC.md#6-gates).

### ICCID

Integrated Circuit Card Identifier — the unique number printed on
the SIM. The daemon reads it to detect SIM swaps.

### IMSI

International Mobile Subscriber Identity — identifies the SIM's
subscriber to the network. Read by the daemon, used for forensics,
not actioned.

### InfraCtrl.script

Zao's helper shell script at `/usr/share/zao/InfraCtrl.script`.
Owns profile programming on the modem (`set_profile_wwan` is the
relevant subcommand). The daemon invokes it; never bypasses it.

### lineN namespace

A Linux network namespace (`line1`, `line2`, ...) that Zao puts each
modem's wwan interface into for traffic isolation. The daemon reads
state via `ip netns exec lineN ...`.

### MCC, MNC

Mobile Country Code (3 digits, 425 = Israel) and Mobile Network Code
(2 digits within an MCC, e.g. 03 = Pelephone). Together they identify
a carrier. The daemon uses (MCC, MNC) to look up the right APN.

### modem_reset

Recovery action: full DMS firmware reset
(`qmicli --dms-set-operating-mode=reset`). Outage ~30–60 s. The
modem comes back as the same `cdc-wdmN` (usually).

### Monotonic clock

`time.monotonic()` — strictly non-decreasing, immune to NTP steps.
Used by the daemon for all backoff and elapsed-time arithmetic.
Distinct from wall clock (`time.time()`), which is used only for
ISO-8601 timestamps.

### PDP context

Packet Data Protocol context. The session a modem opens with the
carrier to get an IP. `--wds-get-packet-service-status` reports its
state.

### Profile #1

The first APN profile in the modem's flash. EM7421 supports many
profiles but Zao only uses #1. Persistent across reboots and resets.

### qmi_wwan

The Linux kernel module that exposes a Sierra-class modem as a wwan
netdev plus a cdc-wdm control device. The daemon never reloads it
unless triggered by the global driver_reset action.

### qmicli

CLI tool from `libqmi-utils`. The daemon's only programmatic interface
to the modem. Output is human-readable text; the `qmi/parsers.py`
module turns it into typed records.

### qmi-proxy

A daemon (started by Zao) that multiplexes QMI access to a modem so
multiple clients (Zao + the daemon + manual qmicli) don't fight for
exclusive ownership of `/dev/cdc-wdmN`. The daemon detects it at
startup and routes through it via `--device-open-proxy`.

### RASCOW_STAT

A log-line type produced by Zao's remote endpoint. Contains the
`active:[1,1,1,1,...]` array that tells us which lines Zao currently
considers operational. The daemon parses these lines via `inotify`
on the Zao log file.

### raw_ip

A flag on a wwan iface (`/sys/class/net/wwanX/qmi/raw_ip`). Must be
`Y` for QMI dialing to work. Sometimes flips to `N` after a
USB/driver event; recovery fixes by writing `Y` back.

### Recovery ladder

The escalation sequence soft_reset → modem_reset → usb_reset → exhausted
applied to issues like `not_registered_searching`. Each rung has a
counter ceiling.

### registration

The state of a modem's attachment to a serving cell. `registered`,
`not_registered_searching`, `denied`, etc. Read via
`--nas-get-serving-system`.

### RF — Radio Frequency

Shorthand for the radio environment. "RF blocked" means the radio
can't decode a usable serving cell, regardless of modem state.

### RSRP, RSRQ, SNR, RSSI

Cellular signal-quality metrics:

- **RSRP** (Reference Signal Received Power, dBm) — strength of the
  reference signals from the serving cell. Threshold: ≥ -110 dBm.
- **RSRQ** (Reference Signal Received Quality, dB) — quality given
  interference and load. Threshold: ≥ -15 dB.
- **SNR** (Signal-to-Noise Ratio, dB) — wanted vs noise. Threshold:
  ≥ 0 dB.
- **RSSI** (Received Signal Strength Indicator, dBm) — total received
  power including everything. Informational only in our policy.

The daemon's `signal.sufficient` is `true` only if RSRP, RSRQ, **and**
SNR all meet thresholds.

### schema_version

An integer carried by every persistent file and wire payload. v2.0
ships at version 1. Daemon refuses to load future schemas; deliberate
migration code (or a tool-driven reset) is required to handle older
schemas if/when one is bumped.

### Sierra EM7421

The modem we use. Sierra Wireless, LTE Cat 7, USB 3, single-SIM,
Sierra VID 1199:9091. Zao-supported and qmi_wwan-supported.

### SIM app

The application running on the SIM card (e.g. USIM). Has its own
state independent of the card's physical presence: `ready`, `detected`,
`pin_required`, etc.

### signal.sufficient

A tri-state in `Diag` per modem: `true`/`false`/`null`. `false` ⇒
RF-blocked, gate destructive resets. `null` ⇒ no reading; proceed.

### SoC

System-on-Chip. The Jetson Orin NX. Thermal sensors are on its
thermal zones; we record but don't action thermal warnings unless
critical.

### soft_reset

Recovery action: SIM power cycle via Zao's
`InfraCtrl.script reset_power_wwan`. Outage ~5 s. The modem stays up.

### sysfs

The kernel's `/sys` filesystem. We use it for USB topology discovery
(`/sys/bus/usb/devices/`), iface state (`/sys/class/net/...`), and
for USB rebind (`/sys/bus/usb/drivers/usb/{bind,unbind}`).

### udev

Kernel hotplug event source. The daemon subscribes to USB add/remove
events to refresh inventory in real time (FR-1).

### usb_reset

Recovery action: sysfs unbind/bind on the USB device. Outage ~10–20 s.
Targeted to one modem.

### wwan / wwanN

The Linux netdev exposed by qmi_wwan for a modem. `wwan0` lives inside
the `lineN` namespace. The daemon never sends traffic over it; Zao does.

### Zao

Shorthand for Soliton's bonding stack: `ZaoInfraCtrl`,
`ZaoRemoteEndpointCloud`. Owns the modems at runtime. The daemon is
explicitly not Zao; it observes and recovers around it.

### Zao log

`/var/log/zao-remote-endpoint.log`. Authoritative source for "is line
N currently bonding?" via `RASCOW_STAT` lines. The daemon tails it
via `inotify`.
