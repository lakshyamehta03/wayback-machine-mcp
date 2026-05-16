from wayback_mcp.client.http import get
from wayback_mcp.client.parsers import parse_cdx, parse_search_archive
from wayback_mcp.config import CDX_URL, CDX_MAX_RESULTS, SEARCH_MAX_RESULTS, SEARCH_URL
from wayback_mcp.models import SearchResult, Snapshot, ToolError, rate_limited_error


def _build_query(
    query: str,
    mediatype: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> str:
    q = query
    if mediatype:
        q += f" AND mediatype:{mediatype}"
    if year_from or year_to:
        lo = str(year_from) if year_from else "*"
        hi = str(year_to) if year_to else "*"
        q += f" AND year:[{lo} TO {hi}]"
    return q


async def search_archive(
    query: str,
    mediatype: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int | None = None,
) -> list[SearchResult] | ToolError:
    params: dict[str, str] = {
        "q": _build_query(query, mediatype, year_from, year_to),
        "output": "json",
        "rows": str(min(limit, SEARCH_MAX_RESULTS) if limit else SEARCH_MAX_RESULTS),
        "fl": "identifier,title,mediatype,year,creator,subject,downloads",
    }

    response = await get(SEARCH_URL, "search", params=params)

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "5")
        return rate_limited_error(retry_after)

    try:
        raw = response.json()
    except Exception:
        return []

    return parse_search_archive(raw)


def _match_type(domain: str) -> str:
    return "prefix" if "/" in domain else "domain"


async def search_domain(
    domain: str,
    from_date: str | None = None,
    to_date: str | None = None,
    status_code: str | None = None,
    limit: int | None = None,
) -> list[Snapshot] | ToolError:
    match_type = _match_type(domain)
    params: dict[str, str] = {
        "url": f"*.{domain}" if match_type == "domain" else f"{domain}*",
        "matchType": match_type,
        "output": "json",
        "collapse": "urlkey",
        "limit": str(min(limit, CDX_MAX_RESULTS) if limit else CDX_MAX_RESULTS),
    }
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if status_code:
        params["filter"] = f"statuscode:{status_code}"

    response = await get(CDX_URL, "cdx", params=params)

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "5")
        return rate_limited_error(retry_after)

    try:
        raw = response.json()
    except Exception:
        return []

    return parse_cdx(raw)
