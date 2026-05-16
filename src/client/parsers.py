from typing import List

from wayback_mcp.models import AvailabilityResult, ItemMetadata, SearchResult, Snapshot


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


def _normalize_str_or_list(value) -> list | None:
    if value is None:
        return None
    if isinstance(value, list):
        return value
    return [value]


def parse_item_metadata(data: dict) -> ItemMetadata:
    meta = data.get("metadata", {})
    item = data.get("item") or {}
    files = data.get("files_sample") or []

    return ItemMetadata(
        identifier=meta["identifier"],
        title=meta.get("title"),
        creator=_normalize_str_or_list(meta.get("creator")),
        subject=_normalize_str_or_list(meta.get("subject")),
        year=meta.get("year"),
        mediatype=meta.get("mediatype"),
        description=meta.get("description"),
        downloads=item.get("downloads"),
        item_size=item.get("item_size"),
        file_count=len(files),
        files=files,
    )


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
