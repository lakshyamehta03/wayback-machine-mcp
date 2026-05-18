# ADR-0004: Default `collapse=timestamp:8` for `lookup_snapshots`

**Date:** 2026-05-18
**Status:** Accepted

## Context

`lookup_snapshots(url)` returns CDX captures for a URL. Without server-side de-duplication, CDX returns **one row per crawler hit** — for a popular URL (a news homepage, Wikipedia article, government press page), that's dozens or hundreds of rows per day.

Before this change, `lookup_snapshots` didn't pass any `collapse` parameter, and the default `limit=50` cap meant the result set was routinely consumed by 50 captures from a single afternoon. The agent calling the tool then saw a thick wall of near-identical rows from one moment in time and learned nothing about the URL's history over months or years — the use case the tool exists to support.

CDX provides server-side de-duplication via the `collapse=<field>[:<N>]` parameter, which folds adjacent rows sharing the same value in the chosen field (or its first N characters). `collapse=timestamp:8` collapses on the first 8 digits of timestamp (YYYYMMDD) — one row per day, picked from across the day's captures.

## Decision

`lookup_snapshots` defaults `collapse` to `"timestamp:8"` when the caller doesn't pass one explicitly.

The parameter convention:

- `collapse=None` (Python default) → resolves to `"timestamp:8"`
- `collapse=""` (explicit empty string) → resolves to no collapsing, raw captures
- `collapse="digest"` / `"timestamp:10"` / any other CDX collapse spec → passed through verbatim

## Reasoning

- **One row per day matches the agent's mental model.** When an agent asks "what snapshots exist for this URL?" it wants a temporal overview — first/last seen, gaps, change cadence. Per-crawler-hit rows don't answer that question; per-day rows do.
- **Existing tools already collapse server-side.** `search_domain` has used `collapse=urlkey` since it was introduced; CDX itself treats collapse as the standard way to reduce noise. Defaulting CDX-facing snapshot queries to a sensible collapse is consistent with that established pattern.
- **`""` opt-out is non-ambiguous.** Three-state arguments (None / empty / value) are sometimes awkward in Python APIs, but here each state has a distinct intent: "use a default," "explicitly no behaviour," "explicit value." This is clearer than introducing a separate `no_collapse: bool` flag.
- **Doesn't break advanced callers.** Anyone who wants every capture, content-hash de-duplication, or per-hour rows can ask for that explicitly. The default just changes what naive `lookup_snapshots(url)` calls produce.

## Trade-offs accepted

- **Hides intra-day captures from the default view.** A caller specifically interested in "how often did the page change in a single day" must opt into `collapse=""` or `collapse="timestamp:10"` (per-hour). This trade is correct for the dominant use case but worth knowing.
- **CDX picks the representative row per day.** We don't control which capture in a day surfaces. For most "show me snapshots" use cases this is fine; for forensic use cases the caller should specify `collapse="digest"` (only content-change captures) or disable collapse entirely.
- **Cache key includes the resolved collapse.** A pre-default cached `lookup_snapshots(url=X)` (no collapse param sent) will not be reused after this change, because the new call sends `collapse=timestamp:8`. Acceptable one-time cache miss on upgrade.

## Reconsider when

- A use case emerges where the default of "one row per day" is actively misleading (e.g., a change-detection tool that needs every capture).
- We add a higher-level "URL history overview" tool that should produce different default collapsing.
- CDX changes the semantics of `timestamp:N` (extremely unlikely — it's a stable public API).

## Related

- `src/tools/snapshots.py` — `lookup_snapshots` signature and resolution logic
- `src/server.py` — MCP-exposed wrapper docstring explains `collapse` in plain English
- `tests/test_snapshots.py` — three tests cover default, explicit override, empty-string opt-out
- GitHub issue #27 (items 1 and 2 — items 3+ remain open)
- CDX upstream docs: https://github.com/internetarchive/wayback/blob/master/wayback-cdx-server/README.md
