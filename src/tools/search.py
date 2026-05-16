from wayback_mcp.client.http import get
from wayback_mcp.client.parsers import parse_cdx
from wayback_mcp.config import CDX_URL, CDX_MAX_RESULTS
from wayback_mcp.models import Snapshot, ToolError


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
        return ToolError(error="Rate limited by the Wayback Machine. Try again later.")

    try:
        raw = response.json()
    except Exception:
        return []

    return parse_cdx(raw)
