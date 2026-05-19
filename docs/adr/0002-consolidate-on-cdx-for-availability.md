# ADR-0002: Consolidate availability lookups onto CDX

**Date:** 2026-05-19
**Status:** Accepted
**Supersedes:** [ADR-0001](0001-no-capture-resolver-primitive.md)

## Context

ADR-0001 (2026-05-17) declined to introduce a `resolve_capture` primitive and kept the two-call pattern (`check_availability` → `lookup_snapshots`) inside `get_snapshot_content`. The reasoning rested on two load-bearing claims:

1. **No operational pressure.** "The extra IA round-trip costs no measurable latency we care about."
2. **No second consumer.** "Only one call site composes these two tools today."

Both have since flipped.

1. **Operational pressure is real.** Production testing showed the Wayback Machine's CDX/availability rate limiter throttling `check_availability`, `lookup_snapshots`, and `get_snapshot_content` hard enough to surface as user-visible failures. A `get_snapshot_content` invocation made three upstream requests — two of them in the `"cdx"` bucket — multiplying the chance of hitting the limit. The auth-cookie routing landed in #26 (verified ~4.6× success-rate improvement) applies to CDX but *not* to the availability endpoint, which uses the S3-style `LOW Authorization` header and runs against a different queue.
2. **A second consumer exists.** Once `get_snapshot_content` is collapsed onto a single CDX call (via `lookup_snapshots(closest_to=ts, limit=1)`), `check_availability` becomes a natural second user of the same pattern — it does nothing the same call can't do.

## Decision

Consolidate both `get_snapshot_content` and `check_availability` onto CDX via `lookup_snapshots`:

- `lookup_snapshots` gains `closest_to: str | None`, which flows through to CDX as `closest=<ts>&sort=closest` (preserving closest-in-time semantics that the availability endpoint provided).
- `get_snapshot_content` makes one CDX call instead of three upstream calls.
- `check_availability` projects a `lookup_snapshots(..., limit=1, collapse="")` result into the existing `AvailabilityResult` shape — the public tool contract is unchanged.
- `AVAILABILITY_URL` and `parse_availability` are removed; the wayback `/available` endpoint is no longer reached.

We still do **not** introduce a separate `resolve_capture` primitive. The shared resolution lives in `lookup_snapshots` itself (closest-to mode), which is already a public tool — no new abstraction layer.

## Reasoning

- **Concrete operational win.** Every tool now shares one upstream endpoint (CDX), one rate-limit bucket, and the cookie-auth queue that demonstrably raises success rate under load. The blast radius of CDX degradation is unchanged, but we no longer multiply it by also depending on a second endpoint with worse auth routing.
- **Deletion test now passes.** Two call sites (`check_availability`, `get_snapshot_content`) use the closest-to lookup. The pattern earns its keep.
- **Legibility cost is small.** The change is mechanical: `lookup_snapshots(url, closest_to=ts, limit=1)` reads about as plainly as the previous availability call. We didn't add a hidden indirection; we widened an existing tool by one parameter.
- **Test churn was paid up front.** ~10 unit tests in `test_snapshots.py`, `test_content.py`, and `test_cache.py` were updated to mock CDX instead of the availability endpoint. Trade made consciously against the operational pressure above.

## Reconsider when

- A future IA change makes the availability endpoint meaningfully better than CDX (separate auth ceilings, lower latency, materially different freshness). At that point we re-introduce the availability path — but as a fallback under CDX failure, not as the primary.
- A third consumer of the closest-to resolution appears with non-trivial pre/post-processing. At that point a thin shared helper (still not a class) inside `tools/snapshots.py` may earn its keep over duplicated calls. Until then, two callers of one tool is not a smell.

## Related

- ADR-0001 — the decision this supersedes
- Issue #26 — verified CDX cookie-auth routing impact (~4.6×)
- `src/tools/snapshots.py` — `closest_to` parameter, `check_availability` reimplementation
- `src/tools/content.py` — `get_snapshot_content` single-CDX-call form
