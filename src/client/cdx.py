from typing import List

from wayback_mcp.client.http import get
from wayback_mcp.client.parsers import parse_cdx
from wayback_mcp.config import CDX_MAX_RESULTS, CDX_URL
from wayback_mcp.models import Snapshot, ToolError


async def cdx_query(
    url: str,
    *,
    fields: list[str] | None = None,
    match_type: str | None = None,
    collapse: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    status_code: str | None = None,
    limit: int | None = None,
    fast_latest: bool = False,
) -> List[Snapshot] | ToolError:
    params: dict[str, str] = {
        "url": url,
        "output": "json",
        "limit": str(limit if limit is not None else CDX_MAX_RESULTS),
    }
    if fast_latest:
        params["fastLatest"] = "true"
    if fields:
        params["fl"] = ",".join(fields)
    if match_type:
        params["matchType"] = match_type
    if collapse:
        params["collapse"] = collapse
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if status_code:
        params["filter"] = f"statuscode:{status_code}"

    response = await get(CDX_URL, "cdx", params=params)

    if isinstance(response, ToolError):
        return response

    try:
        raw = response.json()
    except Exception:
        snippet = response.text[:200].replace("\n", " ")
        return ToolError(
            error=f"CDX returned a malformed response (status={response.status_code}): {snippet}"
        )

    return parse_cdx(raw)
