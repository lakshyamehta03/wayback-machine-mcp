from dataclasses import dataclass
from typing import Literal

from bs4 import BeautifulSoup, Tag

WORD_THRESHOLD = 200
LINK_DENSITY_THRESHOLD = 0.5  # reject semantic containers where >50% of words are link text
WORD_CAP = 8000
PLAINTEXT_CAP = 10000

WAYBACK_TOOLBAR_IDS = {"wm-ipp-base", "wm-ipp", "donato", "wm-ipp-print"}

_HTML_MIME_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_PLAIN_MIME_TYPES = frozenset({"text/plain"})

MimeClass = Literal["html", "plain", "declined"]


@dataclass
class ExtractionResult:
    text: str
    method: str  # "main" | "article" | "role-main" | "body-fallback" | "plain-text"
    word_count: int
    truncated: bool


def classify_mime(content_type: str) -> MimeClass:
    """Classify a Content-Type value into an extraction strategy."""
    ct = content_type.lower().split(";")[0].strip()
    if ct in _HTML_MIME_TYPES:
        return "html"
    if ct in _PLAIN_MIME_TYPES:
        return "plain"
    return "declined"


def _count(text: str) -> int:
    return len(text.split())


def _link_density(element: Tag) -> float:
    """Fraction of words inside <a> tags. High density signals navigation."""
    total = _count(element.get_text(separator=" ", strip=True))
    if total == 0:
        return 1.0
    anchor_words = sum(_count(a.get_text(separator=" ", strip=True)) for a in element.find_all("a"))
    return anchor_words / total


def _truncate(text: str, cap: int) -> tuple[str, bool]:
    words = text.split()
    if len(words) > cap:
        return " ".join(words[:cap]), True
    return text, False


def extract_html(html: str) -> ExtractionResult:
    soup = BeautifulSoup(html, "html.parser")

    for el_id in WAYBACK_TOOLBAR_IDS:
        el = soup.find(id=el_id)
        if el:
            el.decompose()

    candidates = [
        (soup.find("main"), "main"),
        (soup.find("article"), "article"),
        (soup.find(attrs={"role": "main"}), "role-main"),
    ]

    for element, method in candidates:
        if element:
            text = element.get_text(separator=" ", strip=True)
            if _count(text) >= WORD_THRESHOLD and _link_density(element) < LINK_DENSITY_THRESHOLD:
                text, truncated = _truncate(text, WORD_CAP)
                return ExtractionResult(text=text, method=method, word_count=_count(text), truncated=truncated)

    for tag in soup(["script", "style"]):
        tag.decompose()

    body = soup.find("body") or soup
    text = body.get_text(separator=" ", strip=True)
    text, truncated = _truncate(text, WORD_CAP)
    return ExtractionResult(text=text, method="body-fallback", word_count=_count(text), truncated=truncated)


def extract_plaintext(text: str) -> ExtractionResult:
    truncated = len(text) > PLAINTEXT_CAP
    clipped = text[:PLAINTEXT_CAP] if truncated else text
    return ExtractionResult(text=clipped, method="plain-text", word_count=_count(clipped), truncated=truncated)
