from typing import List

from wayback_mcp.models import AvailabilityResult, SearchResult, Snapshot


def parse_cdx(raw: list) -> List[Snapshot]:
    if len(raw) <= 1:
        return []
    header = raw[0]
    snapshots = []
    for row in raw[1:]:
        fields = dict(zip(header, row))
        snapshots.append(Snapshot(
            timestamp=fields["timestamp"],
            original_url=fields["original"],
            mimetype=fields["mimetype"],
            status_code=fields["statuscode"],
            digest=fields.get("digest"),
            length=fields.get("length"),
        ))
    return snapshots


def parse_search_archive(data: dict) -> List[SearchResult]:
    try:
        docs = data["response"]["docs"]
    except (KeyError, TypeError):
        return []
    results = []
    for doc in docs:
        try:
            results.append(SearchResult(
                identifier=doc["identifier"],
                title=doc["title"],
                mediatype=doc["mediatype"],
                year=doc.get("year"),
                creator=doc.get("creator"),
                subject=doc.get("subject"),
                downloads=doc.get("downloads"),
            ))
        except (KeyError, TypeError):
            continue
    return results


def parse_availability(url: str, data: dict) -> AvailabilityResult:
    closest = data.get("archived_snapshots", {}).get("closest")
    if not closest:
        return AvailabilityResult(original_url=url, available=False)
    return AvailabilityResult(
        original_url=url,
        available=closest.get("available", False),
        snapshot_url=closest.get("url"),
        timestamp=closest.get("timestamp"),
        status=closest.get("status"),
    )
