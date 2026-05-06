"""webhook/ — outbound HMAC-signed POSTs (Phase 2 Plan 02-08).

Subpackages:
  - sign: stateless HMAC-SHA256 signing of WebhookEnvelope payloads.
  - dedup: per-(modem, kind) cooldown / dedup_count table.
  - dns: pre-resolved DNS cache with stale-window fallback (W-02).
  - poster: bounded asyncio.Queue + retry loop + drain (Phase 2 Task 2).

The poster runs in a SEPARATE asyncio task so the cycle never blocks on
webhook I/O (FR-44.8).
"""
