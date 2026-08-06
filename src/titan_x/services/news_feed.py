"""Real (free, no-key) news ingestion for the Indian market.

Fetches Google News RSS feeds for NSE/BSE market queries and pushes the raw
articles through :class:`NewsEngine` so /news and insight stop being demo-only.
Google News RSS is public, requires no API key, and is reachable from most
datacenters.
"""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from xml.etree import ElementTree

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
    # element text/links and never expands entities or DTDs, so ElementTree is
    # safe here (no external entity resolution is performed).
    root = ElementTree.fromstring(xml_text)  # noqa: S314
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
                "url": url,
                "source_id": f"google-news-{sha256(url.encode('utf-8')).hexdigest()[:16]}",
                "published_at": _parse_rfc2822(published),
                "language": "en",
            }
        )
    return out


async def fetch_google_news(
    queries: list[str] | None = None,
    per_query: int = 10,
    request_timeout: float = 20.0,
) -> list[dict]:
    """Fetch and merge the latest Google News RSS items for the given queries."""
    queries = queries or DEFAULT_QUERIES
    seen: set[str] = set()
    merged: list[dict] = []
    async with httpx.AsyncClient(
        headers=_HEADERS, timeout=request_timeout, follow_redirects=True
    ) as client:
        for query in queries:
            try:
                resp = await client.get(
                    "https://news.google.com/rss/search",
                    params={"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
                )
                resp.raise_for_status()
                items = _parse_rss(resp.text, query)[:per_query]
                for item in items:
                    if item["url"] in seen:
                        continue
                    seen.add(item["url"])
                    merged.append(item)
                logger.info("news_feed_fetched", query=query, items=len(items))
            except Exception as exc:  # noqa: BLE001
                logger.warning("news_feed_fetch_failed", query=query, error=str(exc))
    return merged


async def run_news_ingestion(session_factory, queries: list[str] | None = None) -> dict:
    """Fetch real news from Google News and ingest into the NewsEngine."""
    async with session_factory() as session:
        from titan_x.services.news_engine import NewsEngine

        raw = await fetch_google_news(queries=queries)
        if not raw:
            return {"fetched": 0, "created": 0, "duplicates": 0, "errors": 0, "reason": "no_items"}
        engine = NewsEngine(session)
        stats = await engine.ingest("google_news", raw, run_nlp=False)
        await session.commit()
        logger.info("news_ingestion_complete", fetched=len(raw), **stats)
        return {"fetched": len(raw), **stats}
