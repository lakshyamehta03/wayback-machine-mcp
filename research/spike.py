"""
Spike: snapshot content extraction reliability (issue #6)

Run:
    uv run python research/spike.py

Fetches each fixture URL, applies the extraction heuristic, and prints a
summary + 300-word preview for manual human review.
"""

import asyncio
import re
import sys
import os

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wayback_mcp.client.extractor import extract_html, extract_plaintext  # noqa: E402

FIXTURES: dict[str, tuple[str, str]] = {
    "a_modern_news":  ("Modern news article (2023)",    "https://web.archive.org/web/20230405222853/http://bbcworldnews.com/"),
    "b_modern_blog":  ("Modern blog post (2020)",        "https://web.archive.org/web/20200601200557/http://leiloesnet.blogspot.com/"),
    "c_js_spa":       ("JS-heavy SPA — Airbnb (2013)",   "https://web.archive.org/web/20130420044109/http://airbnb.co.uk/"),
    "d_pre_html5":    ("Pre-HTML5 page — CBS News (2001)","https://web.archive.org/web/20010607085307/http://cbsnews.com/"),
    "e_early_blog":   ("Early-2000s blog (2007)",        "https://web.archive.org/web/20070104083335/http://corruptionnews.com/"),
    "f_pdf":          ("PDF item page (negative case)",  "https://archive.org/details/english-090.pdf"),
    "g_cia_doc":      ("CIA reading room document",      "https://archive.org/details/cia-readingroom-document-cia-rdp96-00788r001700210016-5"),
}

USER_AGENT = "WaybackMCP/1.0 Spike/1.0"
NON_EXTRACTABLE = {"application/pdf", "image/", "video/", "audio/"}


def _add_if_modifier(url: str) -> str:
    """Insert `if_` into a Wayback URL to bypass toolbar injection."""
    m = re.match(r"(https://web\.archive\.org/web/)(\d+)(/.*)", url)
    if m:
        return f"{m.group(1)}{m.group(2)}if_{m.group(3)}"
    return url


def _is_non_extractable(content_type: str) -> bool:
    return any(t in content_type for t in NON_EXTRACTABLE)


async def _process(label: str, description: str, url: str, client: httpx.AsyncClient) -> dict:
    fetch_url = _add_if_modifier(url)
    used_modifier = fetch_url != url

    try:
        response = await client.get(fetch_url, timeout=30.0, follow_redirects=True)
    except Exception as e:
        return {"label": label, "description": description, "error": str(e)}

    content_type = response.headers.get("content-type", "unknown").lower().split(";")[0].strip()

    if response.status_code != 200:
        return {
            "label": label,
            "description": description,
            "status": response.status_code,
            "content_type": content_type,
            "outcome": "non-200",
        }

    if _is_non_extractable(content_type):
        return {
            "label": label,
            "description": description,
            "status": response.status_code,
            "content_type": content_type,
            "outcome": "declined",
        }

    if "text/plain" in content_type:
        result = extract_plaintext(response.text)
    else:
        result = extract_html(response.text)

    return {
        "label": label,
        "description": description,
        "status": response.status_code,
        "content_type": content_type,
        "used_if_modifier": used_modifier,
        "method": result.method,
        "word_count": result.word_count,
        "truncated": result.truncated,
        "preview": " ".join(result.text.split()[:300]),
        "outcome": "extracted",
    }


def _print_result(r: dict) -> None:
    SEP = "=" * 70
    print(f"\n{SEP}")
    print(f"[{r['label']}] {r['description']}")
    print(SEP)

    if "error" in r:
        print(f"  ERROR: {r['error']}")
        return

    print(f"  Status:        {r.get('status', '?')}")
    print(f"  Content-Type:  {r.get('content_type', '?')}")
    outcome = r.get("outcome", "?")

    if outcome == "declined":
        print(f"  Outcome:       DECLINED (non-extractable MIME type)")
        return

    if outcome == "non-200":
        print(f"  Outcome:       NON-200 RESPONSE")
        return

    print(f"  if_ modifier:  {r.get('used_if_modifier')}")
    print(f"  Method:        {r['method']}")
    print(f"  Word count:    {r['word_count']}")
    print(f"  Truncated:     {r['truncated']}")
    print(f"\n  --- Preview (first 300 words) ---")
    print(f"  {r['preview']}")


async def main() -> None:
    print("Wayback MCP — Snapshot Content Extraction Spike")
    print("Fetching fixtures sequentially (rate-limit friendly)...\n")

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        for label, (description, url) in FIXTURES.items():
            result = await _process(label, description, url, client)
            _print_result(result)
            await asyncio.sleep(1.0)  # polite delay between requests

    print("\n\n=== Spike complete. Review previews above for extraction quality. ===")


if __name__ == "__main__":
    asyncio.run(main())
