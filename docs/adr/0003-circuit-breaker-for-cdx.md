# ADR-0003: Per-bucket circuit breaker for outbound IA requests

**Date:** 2026-05-18
**Status:** Accepted

## Context

Empirical probes against live CDX (see ADR-0002 for raw numbers) confirmed that the dominant failure mode is **upstream instability**, not per-client rate limiting:

- 0 × 429 across 90 requests under three different auth schemes.
- 33% 503s + 53% timeouts at 5 rps from a fresh IP under anonymous auth.
- Even after switching to cookie auth (ADR-0002), ~20% of CDX calls still return 503 — IA's load-shedding is real, just less aggressive for authenticated traffic.

The original retry policy in `src/client/http.py` used linear backoff (`1·(attempt+1)` → 1s, 2s) with `MAX_RETRIES=3`. Two failure modes emerged:

1. **Backoff too short.** CDX's observed recovery windows are 5-15 seconds. Linear 1+2s often gave up while the upstream was still recovering, surfacing transient 5xx as final ToolErrors.
2. **No backpressure on sustained degradation.** When CDX was in an extended bad spell, every call exhausted its full 3-attempt retry budget — burning rate-limit tokens, holding semaphore slots, and adding multiplicative latency for the agent — only to fail anyway.

## Decision

Two changes in `src/client/http.py`:

1. **Exponential backoff capped at 30s** — `min(30.0, 2.0 ** attempt)` → 1s, 2s, 4s, 8s, 16s, 30s. Used for both 5xx retry and network-error retry. 429 retains its server-supplied `Retry-After` (separate concern). `MAX_RETRIES` bumped 3 → 5.
2. **Per-bucket circuit breaker** in a new `src/client/circuit_breaker.py` module. State per `rate_key`:
   - **Failure** = any 5xx response OR network-level `httpx.RequestError`.
   - **Not a failure** = 2xx (resets counter), 3xx, non-429 4xx, 429.
   - Trips after `CIRCUIT_BREAKER_THRESHOLD=5` consecutive failures.
   - When tripped, the bucket short-circuits for `CIRCUIT_BREAKER_COOLDOWN_S=30.0` seconds — `get()` returns `ToolError("...is currently degraded — try again in ~30s")` immediately without firing the request, eating a rate token, or queueing on the semaphore.
   - Implicit half-open: after cooldown, the next request goes through; success resets the counter to zero, failure re-trips for another 30s.

## Reasoning

- **Per-bucket isolation** prevents a degraded CDX from affecting `metadata` / `search` / `content` calls — they use distinct buckets and have their own breakers.
- **429 is explicitly not a failure** in the breaker's view. Rate-limit responses indicate "slow down," not "the endpoint is broken." Throttling is the rate limiter's job; degradation is the breaker's.
- **Cache hits bypass the breaker** (stage 1 < stage 2 in `get()`). If we already have valid cached data, returning it is correct even when the breaker is open — we have data, why refuse it?
- **5 consecutive failures** is the smallest threshold that doesn't trip on the natural noise of CDX (we observed 503 rates around 20-50% under load, so 5 in a row is a clear signal of *sustained* degradation, not a flap).
- **30s cooldown** is long enough that we don't immediately stampede a recovering backend, short enough that the agent isn't left blocked for long after a transient outage.
- **Single-process state** is correct for this MCP server. We're not running multiple replicas, so a shared/distributed breaker would be overkill. The breaker resets on process restart, which is fine.

## Trade-offs accepted

- **Tests need explicit breaker reset** between cases. The breaker is a module-level singleton (matching the existing `_rate_limiter` / `_request_semaphore` pattern), so tests that exercise 5xx retries trip it for subsequent tests. Resolved with an autouse fixture in `tests/conftest.py`. Visible in the test fixture; flagged in comments so future contributors don't trip on it.
- **Half-open is implicit, not a named state.** The current implementation lets the next post-cooldown request through and resets on success. A more formal half-open could limit *one* probe request at a time. Not needed today — the rate limiter already throttles enough that we won't stampede a recovering endpoint with concurrent probes.
- **No instrumentation hook yet** — we don't emit metrics or events when the breaker trips. We do log it. Sufficient for a single-user CLI tool; revisit if we ever centralize.

## Reconsider when

- We move to multi-process / multi-replica deployment — the in-memory breaker becomes per-process and effectively meaningless; would need a shared store.
- IA's reliability improves to the point that 5xx is no longer the dominant failure mode (e.g., they fix the load balancer to enforce real quotas with 429s).
- We add per-URL or per-host breakers because we observe one specific URL hot-spotting while others stay healthy — bucket-level is coarse but currently sufficient.
- The 5-failure threshold proves too sensitive (false-trips on real-world noise) or too lenient (lets degraded windows hurt too many callers). Both are tunable via `CIRCUIT_BREAKER_THRESHOLD`.

## Related

- `src/client/circuit_breaker.py` — implementation (63 lines, single class)
- `src/client/http.py` — integration: breaker check at stage 2, record-failure at the 5xx and network-error outcome branches, record-success at the 2xx/3xx/4xx-other branch
- `src/config.py` — `CIRCUIT_BREAKER_THRESHOLD`, `CIRCUIT_BREAKER_COOLDOWN_S`, bumped `MAX_RETRIES = 5`
- `tests/test_circuit_breaker.py` — 8 tests covering backoff schedule, state machine, per-bucket isolation
- `tests/conftest.py` — autouse reset fixture
- GitHub issue #28
- ADR-0002 (auth routing) — addresses a different layer of the same reliability problem
