from wayback_mcp.models import AvailabilityResult


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
