"""Tests for the feed fetcher module — XML parsing and HTTP mocking."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from faultray.feeds.fetcher import (
    FeedArticle,
    _parse_atom,
    _parse_rss,
    _strip_ns,
    _text,
    fetch_all_feeds,
    fetch_feed,
)
from faultray.feeds.sources import FeedSource


# ---------------------------------------------------------------------------
# Helper data
# ---------------------------------------------------------------------------

SAMPLE_RSS = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Security News</title>
    <item>
      <title>Critical vulnerability in OpenSSL</title>
      <link>https://example.com/openssl-vuln</link>
      <description>A critical buffer overflow was discovered.</description>
      <pubDate>Mon, 01 Jan 2025 12:00:00 GMT</pubDate>
      <category>CVE</category>
      <category>OpenSSL</category>
    </item>
    <item>
      <title>DDoS attack on cloud provider</title>
      <link>https://example.com/ddos</link>
      <description>Major cloud provider hit by volumetric DDoS.</description>
      <pubDate>Tue, 02 Jan 2025 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

SAMPLE_ATOM = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Cloud Incidents</title>
  <entry>
    <title>GCP compute outage in us-east1</title>
    <link href="https://status.cloud.google.com/incident/1"/>
    <summary>Compute Engine was unavailable for 45 minutes.</summary>
    <published>2025-01-01T10:00:00Z</published>
  </entry>
  <entry>
    <title>AWS S3 latency spike</title>
    <link href="https://status.aws.amazon.com/s3-latency"/>
    <content>S3 requests in us-west-2 experienced elevated latency.</content>
    <updated>2025-01-02T15:30:00Z</updated>
  </entry>
</feed>
"""

INVALID_XML = b"<not valid xml <<>>"


# ---------------------------------------------------------------------------
# _strip_ns and _text tests
# ---------------------------------------------------------------------------

class TestStripNs:
    def test_strips_namespace(self):
        assert _strip_ns("{http://www.w3.org/2005/Atom}title") == "title"

    def test_no_namespace(self):
        assert _strip_ns("title") == "title"

    def test_empty_string(self):
        assert _strip_ns("") == ""


class TestText:
    def test_none_element(self):
        assert _text(None) == ""

    def test_element_with_text(self):
        import xml.etree.ElementTree as ET
        elem = ET.fromstring("<title>Hello World</title>")
        assert _text(elem) == "Hello World"

    def test_element_with_whitespace(self):
        import xml.etree.ElementTree as ET
        elem = ET.fromstring("<title>  spaced  </title>")
        assert _text(elem) == "spaced"

    def test_element_no_text(self):
        import xml.etree.ElementTree as ET
        elem = ET.fromstring("<title/>")
        assert _text(elem) == ""


# ---------------------------------------------------------------------------
# RSS parsing tests
# ---------------------------------------------------------------------------

class TestParseRss:
    def test_parses_items(self):
        source = FeedSource(name="Test RSS", url="https://example.com/rss", tags=["test"])
        articles = _parse_rss(SAMPLE_RSS, source)
        assert len(articles) == 2

    def test_first_article_fields(self):
        source = FeedSource(name="Test RSS", url="https://example.com/rss", tags=["security"])
        articles = _parse_rss(SAMPLE_RSS, source)
        art = articles[0]
        assert art.title == "Critical vulnerability in OpenSSL"
        assert art.link == "https://example.com/openssl-vuln"
        assert "buffer overflow" in art.summary
        assert art.source_name == "Test RSS"
        assert "CVE" in art.tags
        assert "OpenSSL" in art.tags
        assert "security" in art.tags  # source tag

    def test_second_article(self):
        source = FeedSource(name="Test RSS", url="https://example.com/rss", tags=[])
        articles = _parse_rss(SAMPLE_RSS, source)
        art = articles[1]
        assert art.title == "DDoS attack on cloud provider"

    def test_invalid_xml_returns_empty(self):
        source = FeedSource(name="Bad", url="https://example.com/bad")
        articles = _parse_rss(INVALID_XML, source)
        assert articles == []

    def test_empty_feed(self):
        empty_rss = b"<?xml version='1.0'?><rss><channel></channel></rss>"
        source = FeedSource(name="Empty", url="https://example.com/empty")
        articles = _parse_rss(empty_rss, source)
        assert articles == []


# ---------------------------------------------------------------------------
# Atom parsing tests
# ---------------------------------------------------------------------------

class TestParseAtom:
    def test_parses_entries(self):
        source = FeedSource(name="Test Atom", url="https://example.com/atom", feed_type="atom", tags=["cloud"])
        articles = _parse_atom(SAMPLE_ATOM, source)
        assert len(articles) == 2

    def test_first_entry_fields(self):
        source = FeedSource(name="Test Atom", url="https://example.com/atom", feed_type="atom", tags=["gcp"])
        articles = _parse_atom(SAMPLE_ATOM, source)
        art = articles[0]
        assert art.title == "GCP compute outage in us-east1"
        assert "status.cloud.google.com" in art.link
        assert "unavailable" in art.summary
        assert art.source_name == "Test Atom"
        assert "gcp" in art.tags

    def test_second_entry_uses_content(self):
        source = FeedSource(name="Test Atom", url="https://example.com/atom", feed_type="atom", tags=[])
        articles = _parse_atom(SAMPLE_ATOM, source)
        art = articles[1]
        assert art.title == "AWS S3 latency spike"
        assert "elevated latency" in art.summary

    def test_invalid_xml_returns_empty(self):
        source = FeedSource(name="Bad", url="https://example.com/bad", feed_type="atom")
        articles = _parse_atom(INVALID_XML, source)
        assert articles == []


# ---------------------------------------------------------------------------
# FeedArticle
# ---------------------------------------------------------------------------

class TestFeedArticle:
    def test_full_text_property(self):
        art = FeedArticle(
            title="DDoS Attack",
            link="https://example.com",
            summary="Major volumetric attack observed",
            published="2025-01-01",
            source_name="test",
        )
        full = art.full_text
        assert "ddos attack" in full
        assert "volumetric attack" in full


# ---------------------------------------------------------------------------
# Async fetch tests (mocked HTTP)
# ---------------------------------------------------------------------------

class TestFetchFeed:
    @pytest.mark.asyncio
    async def test_fetch_rss_feed(self):
        source = FeedSource(name="Mock RSS", url="https://example.com/rss", tags=["test"])

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = SAMPLE_RSS
        mock_response.raise_for_status = lambda: None

        with patch("faultray.feeds.fetcher.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            articles = await fetch_feed(source)
            assert len(articles) == 2
            assert articles[0].title == "Critical vulnerability in OpenSSL"

    @pytest.mark.asyncio
    async def test_fetch_atom_feed(self):
        source = FeedSource(name="Mock Atom", url="https://example.com/atom", feed_type="atom", tags=["cloud"])

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = SAMPLE_ATOM
        mock_response.raise_for_status = lambda: None

        with patch("faultray.feeds.fetcher.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            articles = await fetch_feed(source)
            assert len(articles) == 2

    @pytest.mark.asyncio
    async def test_fetch_http_error_returns_empty(self):
        import httpx
        source = FeedSource(name="Error", url="https://example.com/fail")

        with patch("faultray.feeds.fetcher.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.HTTPError("connection failed")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            articles = await fetch_feed(source)
            assert articles == []


class TestFetchAllFeeds:
    @pytest.mark.asyncio
    async def test_fetch_all_skips_disabled(self):
        sources = [
            FeedSource(name="Enabled", url="https://example.com/1", enabled=True),
            FeedSource(name="Disabled", url="https://example.com/2", enabled=False),
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = SAMPLE_RSS
        mock_response.raise_for_status = lambda: None

        with patch("faultray.feeds.fetcher.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            articles = await fetch_all_feeds(sources)
            # Only the enabled source was fetched
            assert len(articles) == 2  # 2 items from the single RSS feed

    @pytest.mark.asyncio
    async def test_fetch_all_handles_exceptions(self):
        sources = [
            FeedSource(name="Fail", url="https://example.com/fail", enabled=True),
        ]

        with patch("faultray.feeds.fetcher.fetch_feed", side_effect=Exception("boom")):
            articles = await fetch_all_feeds(sources)
            # Exceptions are caught and empty list is returned
            assert articles == []
