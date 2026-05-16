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


class DomainUrl(BaseModel):
    url: str
    timestamp: str
    status_code: str
    mimetype: str


class SearchResult(BaseModel):
    identifier: str
    title: str
    mediatype: str
    year: Optional[Union[int, str]] = None
    creator: Optional[Union[str, List[str]]] = None
    subject: Optional[Union[str, List[str]]] = None
    downloads: Optional[int] = None


class ItemMetadata(BaseModel):
    identifier: str
    title: Optional[str] = None
    creator: Optional[Union[str, List[str]]] = None
    subject: Optional[Union[str, List[str]]] = None
    year: Optional[str] = None
    mediatype: Optional[str] = None
    description: Optional[Union[str, List[str]]] = None
    downloads: Optional[int] = None
    item_size: Optional[int] = None
    file_count: int = 0
    files: List[dict] = []


class ToolError(BaseModel):
    error: str
