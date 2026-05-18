# ADR-0002: Route IA auth by URL — Cookie for CDX, `Authorization: LOW` for everything else

**Date:** 2026-05-18
**Status:** Accepted

## Context

`src/client/http.py` was sending `Authorization: LOW {access}:{secret}` on every outbound request when IA credentials were configured. This is the S3-style scheme IA documents for the metadata, search, and availability endpoints.

While investigating empty CDX results (#23), an empirical probe (`/tmp/cdx_auth_verify.py`, gitignored) tested three auth schemes against the live CDX server at 5 rps over 30 requests each:

| scheme | 200 | 503 | network errors | 429 |
|---|---|---|---|---|
| anonymous | 4 | 10 | 16 | 0 |
| Authorization: LOW | 1 | 11 | 18 | 0 |
| Cookie: cdx-auth-token | 4 | 0 | 26 | 0 |

The cookie scheme had **zero 503s** vs ~33% under the other two — the failure pattern genuinely shifted. A follow-up probe at our production parameters (1 rps, 30s timeout, cookie auth only) measured **60% success vs the prior ~13%**, a 4.6x improvement. Successful calls were also faster on average (15.7s vs longer-tail timeouts).

Interpretation: IA's CDX server accepts API keys via cookie (`cdx-auth-token=ACCESS-SECRET`, hyphen-separated) and routes authenticated traffic into a **queue** instead of fast-failing at the load balancer with 503. Anonymous and `Authorization: LOW` traffic both get rejected upfront under load. The auth scheme is the routing key, not a quota gate (zero 429s under any scheme — there is no per-client quota being enforced on these read endpoints).

## Decision

In `src/client/http.py`, route auth by the request URL:

- `url.startswith(CDX_URL)` → `Cookie: cdx-auth-token=ACCESS-SECRET`
- everything else → `Authorization: LOW ACCESS:SECRET` (unchanged)

Never send both on the same request — IA's behavior with both headers is undefined.

When credentials aren't configured, neither is sent (anonymous behavior preserved exactly).

## Reasoning

- **Empirically the right scheme for CDX.** The 60% vs 13% delta is well outside noise; the 4.6x improvement is the load-bearing reliability win in this round of changes.
- **`Authorization: LOW` is correct for the S3-style endpoints.** Metadata, availability, and search are conventional IA APIs that expect that header. Switching them all to cookie auth would be unverified and might silently degrade other endpoints.
- **URL routing is more honest than rate-key routing.** Our `rate_key="cdx"` bucket is overloaded — it covers both the CDX server (`web.archive.org/cdx/search/cdx`) AND the availability API (`archive.org/wayback/available`), which share rate-limit semantics but are different services. The cookie was only verified to help on the CDX server itself; routing on the URL prefix scopes the change tightly to what was tested.
- **Cookie vs header is otherwise interchangeable.** Both are static-string request headers; cookies aren't stateful in this design (the value is the API key, never changes, never refreshed). No cookie jar, no expiry, no session.

## Trade-offs accepted

- **Higher per-call latency on CDX** (~15s avg success vs prior fast-fail). The latency cost is real and substantial — but for this tool's research-oriented use case, slow real results beat fast empty results. Users explicitly preferred this trade.
- **20% of CDX calls still return 503.** Cookie auth raises priority but doesn't bypass IA's load-shedding entirely. The residual is addressed separately by the retry + circuit breaker work (ADR-0003).
- **Per-key burst limit.** The probe at 5 rps eventually triggered immediate `ConnectError`s after ~24 requests — likely an authenticated-traffic burst limit IA only enforces on identifiable keys. At our production 1 rps with `MAX_CONCURRENT_REQUESTS=4` we shouldn't trip it, but it's a latent risk if those settings rise.

## Reconsider when

- IA changes the cookie format (e.g., requires a different separator, expects encryption, ships an OAuth flow).
- A new IA endpoint joins the codebase that needs different auth treatment — generalize the routing then, don't preemptively.
- Cookie auth's benefit narrows (e.g., IA fixes CDX's load-shedding so anon traffic stops getting fast-failed).
- A new use case needs the prior fast-empty-vs-slow-real trade-off inverted.

## Related

- `src/client/http.py` — `_build_auth(url)` helper and call site in `get()`
- `tests/test_auth.py` — three new tests cover CDX+creds (cookie only), CDX without creds (neither), non-CDX with creds (Authorization only)
- GitHub issue #26 — opened, closed once as "no-op," reopened with the follow-up probe data, then closed for real with this implementation
- `/tmp/cdx_auth_verify.py` and `/tmp/cdx_cookie_probe.py` — gitignored verification scripts
