from typing import List, Optional, Union
from pydantic import BaseModel


class AvailabilityResult(BaseModel):
    original_url: str
    available: bool
    snapshot_url: Optional[str] = None
    timestamp: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None


class Snapshot(BaseModel):
    timestamp: str
    original_url: str
    status_code: str
    mimetype: str
    digest: Optional[str] = None
    length: Optional[str] = None

    @property
    def wayback_url(self) -> str:
        return f"https://web.archive.org/web/{self.timestamp}/{self.original_url}"

    @property
    def content_url(self) -> str:
        return f"https://web.archive.org/web/{self.timestamp}if_/{self.original_url}"


class ToolError(BaseModel):
    error: str
