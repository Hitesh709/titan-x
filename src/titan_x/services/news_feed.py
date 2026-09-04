"""Real (free, no-key) news ingestion for the Indian market.

Fetches Google News RSS feeds for NSE/BSE market queries and pushes the raw
articles through :class:`NewsEngine` so /news and insight stop being demo-only.
Google News RSS is public, requires no API key, and is reachable from most
datacenters.
"""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from xml.etree import ElementTree  # nosec B405 - DTD/entity expansion is not used

import httpx
import structlog

logger = structlog.get_logger(__name__)

DEFAULT_QUERIES = [
    "NSE OR BSE OR Sensex OR Nifty",
    "Indian stock market",
    "RBI OR inflation OR GDP India",
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}


def _parse_rfc2822(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except (ValueError, TypeError):
        return None


def _namespace_map(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _parse_rss(xml_text: str, query: str) -> list[dict]:
    # Google News RSS is remote, non-authenticated input; the parser only reads
    # element text/links and never expands entities or DTDs.
    root = ElementTree.fromstring(xml_text)  # nosec B314 - RSS parser has no DTD/entity use
    out: list[dict] = []
    for item in root.iter("item"):
        title = summary = url = None
        published = None
        for child in item:
            name = _namespace_map(child.tag)
            if name == "title":
                title = (child.text or "").strip()
            elif name == "description":
                summary = (child.text or "").strip()
            elif name == "link":
                url = (child.text or "").strip()
            elif name == "pubDate":
                published = child.text or None
        if not title or not url:
            continue
        out.append(
            {
                "title": title,
                "summary": summary[:2000] if summary else None,