# ADR-0001: No `Capture` resolver primitive — keep `check_availability` + CDX MIME pre-check inline

**Date:** 2026-05-17
**Status:** Superseded by [ADR-0002](0002-consolidate-on-cdx-for-availability.md) (2026-05-19)

## Context

`get_snapshot_content` (`src/tools/content.py:9-48`) resolves a URL+timestamp to a fetchable archived page in two IA round-trips:

1. `check_availability` → resolved snapshot URL, actual captured timestamp
2. `lookup_snapshots(url, from_date=ts, to_date=ts, limit=1)` → MIME type, for the extraction-strategy branch

An architecture review surfaced this as a deepening opportunity: introduce a `resolve_capture(url, timestamp) -> ResolvedCapture` primitive (likely in `src/client/`) that returns `{snapshot_url, timestamp, mimetype, status_code}` in one CDX call using `closest=`, and rename the missing domain concept to **Capture** in `CONTEXT.md`.

## Decision

Do not introduce the resolver. Keep the two-call pattern in `get_snapshot_content`.

## Reasoning

- **Deletion test fails.** Only one call site composes these two tools today (`get_snapshot_content`). Deleting the hypothetical `resolve_capture` would re-concentrate complexity in exactly one place — the signal of a premature abstraction, not a deepening.
- **No operational pressure.** The extra IA round-trip costs no measurable latency we care about and shares the `"cdx"` rate-limit bucket with the first call. There is no user-visible problem forcing the change.
- **Legibility cost.** Reading `content.py` top-to-bottom currently tells the reader exactly what is happening: check archived → look up MIME → branch on MIME. A resolver hides that flow behind a name; worthwhile when the flow is repeated, noise when it is used once.
- **Test churn is real and concrete.** ~8 unit tests in `tests/test_content.py` mock all three endpoints (`AVAILABILITY_URL`, `CDX_URL`, `_CONTENT_URL`). Collapsing the resolution into a single CDX call would require rewriting their `respx` setup. That cost is paid up front against speculative benefits.
- **Speculative leverage.** The case for the abstraction rested on "future composing tools will reuse it." No second consumer is on the roadmap. Designing for hypothetical future callers is the antipattern the project's CLAUDE.md explicitly warns against.

## Reconsider when

A second tool genuinely needs to resolve a URL+timestamp to `{snapshot_url, timestamp, mimetype}` (for example: a diffing tool, a citation tool, or a "fetch raw bytes" tool that also needs MIME pre-classification). At that point the deletion test flips — the concept earns its keep across multiple call sites — and the test churn becomes worth paying.

Until then, treat the two-call pattern as honest plumbing, not a code smell.

## Related

- Architecture review conversation, 2026-05-17
- `src/tools/content.py:9-48` — current implementation
- `CONTEXT.md` — no **Capture** term added (would be the side effect if this ADR were ever reversed)
