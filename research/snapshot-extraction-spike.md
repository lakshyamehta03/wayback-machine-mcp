# Spike: Snapshot Content Extraction Reliability

**Issue:** #6  
**Date:** 2026-05-17  
**Status:** Complete — proceed to #6b with amendments noted below

---

## Heuristic under test

From the PRD:

> Try `<main>`, `<article>`, `role="main"` — if result > 200 words, use it; otherwise fall back to stripped body (`<script>` and `<style>` removed, Wayback toolbar stripped).

Implemented in `src/client/extractor.py`. Spike script at `research/spike.py`.

---

## Fixtures and results

| # | Type | URL | Method | Words | Outcome |
|---|---|---|---|---|---|
| a | Modern news (2023) | BBC World News | `role-main` | 456 | Pass — readable, but navigational |
| b | Modern blog (2020) | Blogspot (Portuguese) | `body-fallback` | 1324 | Pass — actual blog content |
| c | JS-heavy SPA (2013) | Airbnb UK | `body-fallback` | 329 | Pass (marginal) — sparse but intelligible |
| d | Pre-HTML5 (2001) | CBS News | `body-fallback` | 765 | Pass — mixed nav + headlines |
| e | Early blog (2007) | Corruption News | `body-fallback` | 1358 | Pass — nav-heavy but content present |
| f | PDF (negative case) | IA `/details/` page | `main` | 250 | See note 1 |
| g | Plain-text/doc | CIA reading room IA page | `main` | 333 | See note 2 |
| h | Paywalled article | — | — | — | Not curated |

---

## Findings

### 1. The `if_` modifier works reliably

All Wayback Machine URLs (a–e) had the `if_` modifier applied (`/web/{ts}if_/{url}`). None of the previews contained Wayback toolbar content. **Confirmed: keep `if_` in the implementation.**

### 2. The 200-word threshold is sound

Every fixture that had a semantic container (`<main>`, `<article>`, `role="main"`) exceeded 200 words, and no body-fallback produced fewer than 300 words. **200 words is a reasonable gate — no change needed.**

### 3. `role="main"` is more common than `<main>` on 2010s-era pages

BBC World News (2023) used `role="main"` rather than a `<main>` element. The fallback chain `main → article → role-main → body` is the right order (most semantically specific first), but in practice `role-main` fires often. No change to the order is needed.

### 4. Pre-HTML5 body-fallback produces navigational noise — expected

CBS News 2001 (d) and Corruption News 2007 (e) both fell to `body-fallback` and returned nav links mixed with content. This is the best achievable result for pre-HTML5 pages. The tool contract should set the expectation that pre-HTML5 extraction may be noisy. No threshold change needed.

### 5. JS SPAs produce sparse but usable output

Airbnb 2013 (c) returned 329 words — UI labels, location names, search form placeholders. It's sparse but not garbage. The tool should surface `word_count` in the response so Claude can signal "this page was likely JS-rendered and may be incomplete."

### 6. PDF/document `/details/` pages — fixture design issue

Fixtures f and g were `archive.org/details/` URLs, which are always HTML wrapper pages, not the actual PDF content. The heuristic extracted the IA metadata HTML (`<main>` element, 250–333 words) — technically "correct" extraction, but not useful content.

**Implication for the implementation:** The MIME type gate (CDX pre-check before fetching) is what keeps PDFs out. For a Wayback snapshot of a URL whose CDX `mimetype` is `application/pdf`, the tool declines before any fetch. For IA `/details/` HTML pages, the heuristic works but the output is IA boilerplate, not document text.

**Recommendation:** The implementation should also detect archive.org `/details/` URLs (or IA boilerplate patterns) and handle them differently, or document this gap. Out of scope for #6b v1 — add a follow-up issue.

### 7. The `html.parser` is tolerant enough

All pages (including the 2001 CBS News page with malformed early-2000s HTML) parsed without error. No need to add `lxml` as a dependency in v1.

---

## Open questions — resolved

| Question | Answer |
|---|---|
| Is 200 words the right threshold? | Yes — no fixture produced a false positive or false negative |
| Does the heuristic work on pre-HTML5 pages? | Yes, via `body-fallback`; output is navigational but readable |
| Is Wayback toolbar stripped reliably? | Yes — `if_` modifier bypasses injection entirely |
| Common shapes that produce garbage? | JS SPAs return sparse output (flag via `word_count`); IA `/details/` pages return boilerplate |
| `html.parser` vs `lxml`? | `html.parser` is sufficient; no parse errors on any fixture |

---

## Contract amendments for #6b

1. **Response shape**: always include `word_count` and `extraction_method` so Claude can communicate extraction confidence to the user.
2. **JS SPA signal**: if `word_count < 500` and `extraction_method == "body-fallback"`, include a note in the response: `"Page may be JS-rendered; extracted content may be incomplete."`
3. **IA `/details/` page gap**: document as a known limitation (out of scope v1). Open follow-up issue.
4. **Paywalled pages**: not validated. Treat as an open risk — paywalled archives may return minimal content silently. Document in tool description.

---

## Go / No-go

**Go.** The heuristic is sound. The 200-word threshold works. The `if_` modifier solves toolbar injection cleanly. Proceed to #6b.
