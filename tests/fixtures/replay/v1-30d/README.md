# v1-30d Replay Traces

This directory contains >=30 days of v1 historical traces, used by the
HIL replay-harness 30-day agreement gate (Phase 4 SC#4 / CONTEXT D-03).

## Status

Initially empty. JSON shards are checked in via Git LFS (see
`.gitattributes`). The `.gitkeep` ensures the directory exists even
when no traces are present.

## Refresh cadence

Quarterly OR on parser changes that invalidate prior fixtures.

## How to refresh

1. SSH into a representative production Jetson with v1 deployed.
2. Run the v1 trace exporter (see `docs/MIGRATION.md` §0 / Phase 0
   trace capture procedure):

   ```bash
   sudo /usr/local/bin/diag.sh --capture-trace --since=30d \
     --output=/tmp/v1-30d-traces.tgz
   ```

3. On the dev laptop, extract and redact:

   ```bash
   tar xzf v1-30d-traces.tgz
   python tools/redact_traces.py \
     --input ./v1-30d-traces/ \
     --output tests/fixtures/replay/v1-30d/
   ```

   (`tools/redact_traces.py` is a future helper; until it is written,
   redact manually per the contract below.)

4. Commit the redacted shards via Git LFS:

   ```bash
   git lfs track "tests/fixtures/replay/v1-30d/*.json"
   git add tests/fixtures/replay/v1-30d/
   git commit -m "fixtures(v1-30d): refresh quarterly snapshot"
   git push
   ```

## Redaction contract (per CONTEXT D-03)

ALL of the following fields MUST be replaced with
`<redacted:<8-hex-chars>>` where the 8 hex chars are the first 8 of
`sha256(value)`:

- `iccid` (any value matching `^[0-9]{18,22}$`)
- `imsi` (any value matching `^[0-9]{14,15}$`)
- IPv4 addresses (any value matching the standard dotted-quad regex)
- IPv6 addresses (any colon-separated hex value of the right shape)

Same redaction shape as Plan 02-09's `ctl support-bundle` (sha256[:8]
hash). Same identity → same redacted value (deterministic — enables
identity correlation in the redacted output without exposing PII).

The HMAC secret is NEVER copied. The webhook URL hostname is preserved
(for DNS pre-resolve correctness) but the path/query is stripped.

## Fixture-directory shape

Matches `tests/fixtures/replay/<scenario>/<NNN>.json` per Phase 2's
`gen_replay_fixtures.py` shape (each JSON file is one cycle's `Diag`
input + v1's planned action output). Plan 02-10 replay harness already
understands this shape — point it at this directory.

## How the HIL workflow consumes this directory

1. `.github/workflows/hil.yml` setup step runs
   `python -m tools.pull_replay_traces` (Plan 04-06).
2. `tools/pull_replay_traces.py` invokes
   `git lfs pull --include tests/fixtures/replay/v1-30d/`.
3. The HIL scenario suite (Plan 04-07) invokes the replay harness
   against this directory after the bench-Jetson scenarios complete.
4. Pass criterion: fault-cycle agreement >=95% (per FR-24 SC#4 last
   paragraph + CONTEXT D-03).
