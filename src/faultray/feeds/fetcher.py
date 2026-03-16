"""Fetch and parse RSS/Atom feeds from security news sources."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import httpx

from faultray.feeds.sources import FeedSource

logger = logging.getLogger(__name__)


@dataclass
class FeedArticle:
    """A single article from a security news feed."""

    title: str
    link: str
    summary: str
    published: str
    source_name: str
    tags: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Combined title + summary for pattern matching."""
        return f"{self.title} {self.summary}".lower()


def _strip_ns(tag: str) -> str:
    """Remove XML namespace prefix from tag."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _text(elem: ET.Element | None) -> str:
    """Safely extract text from an XML element."""
    if elem is None:
        return ""
    return (elem.text or "").strip()


def _parse_rss(xml_bytes: bytes, source: FeedSource) -> list[FeedArticle]:
    """Parse RSS 2.0 feed."""
    articles: list[FeedArticle] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.warning("Failed to parse RSS from %s: %s", source.name, e)
        return articles

    # RSS items live under <channel><item>
    for item in root.iter("item"):
        title = _text(item.find("title"))
        link = _text(item.find("link"))
        desc = _text(item.find("description"))
        pub = _text(item.find("pubDate"))

        # Collect category tags
        cats = [_text(c) for c in item.findall("category") if _text(c)]

        if title:
            articles.append(FeedArticle(
                title=title,
                link=link,
                summary=desc[:1000],  # Truncate very long descriptions
                published=pub,
                source_name=source.name,
                tags=source.tags + cats,
            ))
    return articles


def _parse_atom(xml_bytes: bytes, source: FeedSource) -> list[FeedArticle]:
    """Parse Atom feed."""
    articles: list[FeedArticle] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.warning("Failed to parse Atom from %s: %s", source.name, e)
        return articles

    for entry in root.iter():
        if _strip_ns(entry.tag) != "entry":
            continue

        title = ""
        link = ""
        summary = ""
        published = ""

        for child in entry:
            tag = _strip_ns(child.tag)
            if tag == "title":
                title = (child.text or "").strip()
            elif tag == "link":
                link = child.get("href", "") or (child.text or "").strip()
            elif tag in ("summary", "content"):
                summary = (child.text or "").strip()[:1000]
            elif tag in ("published", "updated"):
                published = (child.text or "").strip()

        if title:
            articles.append(FeedArticle(
                title=title,
                link=link,
                summary=summary,
                published=published,
                source_name=source.name,
                tags=source.tags,
            ))
    return articles


async def fetch_feed(source: FeedSource, timeout: float = 15.0) -> list[FeedArticle]:
    """Fetch and parse a single feed source."""
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": "FaultRay/1.0 (chaos-engineering-simulator)"},
    ) as client:
        try:
            resp = await client.get(source.url)
            resp.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException):
            return []

    if source.feed_type == "atom":
        return _parse_atom(resp.content, source)
    return _parse_rss(resp.content, source)


async def fetch_all_feeds(
    sources: list[FeedSource],
    timeout: float = 15.0,
) -> list[FeedArticle]:
    """Fetch all feed sources concurrently."""
    import asyncio

    tasks = [fetch_feed(s, timeout=timeout) for s in sources if s.enabled]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    articles: list[FeedArticle] = []
    for result in results:
        if isinstance(result, list):
            articles.extend(result)
    return articles
