"""Default security news feed sources."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FeedSource:
    """A security news RSS/Atom feed source."""

    name: str
    url: str
    feed_type: str = "rss"  # rss | atom
    enabled: bool = True
    tags: list[str] = field(default_factory=list)


# Curated list of infrastructure/security incident feeds
DEFAULT_SOURCES: list[FeedSource] = [
    # --- Major incident / outage feeds ---
    FeedSource(
        name="CISA Alerts",
        url="https://www.cisa.gov/cybersecurity-advisories/all.xml",
        tags=["cve", "vulnerability", "government"],
    ),
    FeedSource(
        name="NIST NVD",
        url="https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss.xml",
        tags=["cve", "vulnerability"],
    ),
    FeedSource(
        name="The Hacker News",
        url="https://feeds.feedburner.com/TheHackersNews",
        tags=["security", "incident", "breach"],
    ),
    FeedSource(
        name="BleepingComputer",
        url="https://www.bleepingcomputer.com/feed/",
        tags=["security", "malware", "incident"],
    ),
    FeedSource(
        name="AWS Security Bulletins",
        url="https://aws.amazon.com/security/security-bulletins/feed/",
        feed_type="atom",
        tags=["aws", "cloud", "vulnerability"],
    ),
    FeedSource(
        name="Google Cloud Incidents",
        url="https://status.cloud.google.com/feed.atom",
        feed_type="atom",
        tags=["gcp", "cloud", "outage"],
    ),
    FeedSource(
        name="Krebs on Security",
        url="https://krebsonsecurity.com/feed/",
        tags=["security", "breach", "incident"],
    ),
    FeedSource(
        name="Ars Technica Security",
        url="https://feeds.arstechnica.com/arstechnica/security",
        tags=["security", "incident"],
    ),
]


def get_enabled_sources() -> list[FeedSource]:
    """Return only enabled feed sources."""
    return [s for s in DEFAULT_SOURCES if s.enabled]
