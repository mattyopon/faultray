"""Tests for the security news feed integration."""

from __future__ import annotations

from faultray.feeds.analyzer import (
    AnalyzedIncident,
    IncidentPattern,
    analyze_articles,
    incidents_to_scenarios,
)
from faultray.feeds.fetcher import FeedArticle
from faultray.feeds.store import (
    clear_store,
    load_feed_scenarios,
    save_feed_scenarios,
)
from faultray.model.components import Component, ComponentType, ResourceMetrics, Capacity
from faultray.simulator.scenarios import FaultType


def _make_article(title: str, summary: str = "", source: str = "test") -> FeedArticle:
    return FeedArticle(
        title=title,
        link=f"https://example.com/{title[:20].replace(' ', '-')}",
        summary=summary,
        published="2025-01-01",
        source_name=source,
    )


def test_analyze_ddos_article():
    articles = [_make_article("Massive DDoS attack hits major cloud provider")]
    incidents = analyze_articles(articles)
    assert len(incidents) > 0
    assert any(i.pattern.id == "ddos_volumetric" for i in incidents)


def test_analyze_ransomware_article():
    articles = [_make_article("New ransomware variant encrypts all data")]
    incidents = analyze_articles(articles)
    assert len(incidents) > 0
    assert any(i.pattern.id == "ransomware" for i in incidents)


def test_analyze_memory_leak_article():
    articles = [_make_article("Critical memory leak causes OOM crash in production")]
    incidents = analyze_articles(articles)
    assert len(incidents) > 0
    assert any(i.pattern.id == "memory_leak_incident" for i in incidents)


def test_analyze_no_match():
    articles = [_make_article("New JavaScript framework released today")]
    incidents = analyze_articles(articles)
    assert len(incidents) == 0


def test_analyze_multiple_patterns():
    articles = [
        _make_article("DDoS attack took down services"),
        _make_article("Database corruption causes data loss"),
        _make_article("Redis cache failure causes stampede"),
    ]
    incidents = analyze_articles(articles)
    pattern_ids = {i.pattern.id for i in incidents}
    assert "ddos_volumetric" in pattern_ids
    assert "db_corruption" in pattern_ids
    assert "cache_incident" in pattern_ids


def test_incidents_to_scenarios_generic():
    articles = [_make_article("Major DDoS denial of service flood")]
    incidents = analyze_articles(articles)
    scenarios = incidents_to_scenarios(incidents, ["server-1", "server-2"])
    assert len(scenarios) > 0
    assert all(s.name.startswith("[FEED]") for s in scenarios)


def test_incidents_to_scenarios_component_aware():
    articles = [_make_article("Redis cache failure and eviction storm")]
    incidents = analyze_articles(articles)

    components = {
        "nginx": Component(
            id="nginx", name="nginx", type=ComponentType.LOAD_BALANCER,
            host="web01", port=443, replicas=1,
            metrics=ResourceMetrics(cpu_percent=20, memory_percent=30),
            capacity=Capacity(max_connections=10000),
        ),
        "redis": Component(
            id="redis", name="redis", type=ComponentType.CACHE,
            host="cache01", port=6379, replicas=1,
            metrics=ResourceMetrics(cpu_percent=10, memory_percent=50),
            capacity=Capacity(max_connections=10000),
        ),
    }

    scenarios = incidents_to_scenarios(
        incidents, list(components.keys()), components
    )
    assert len(scenarios) > 0
    # Cache incident should target the redis component
    for s in scenarios:
        for f in s.faults:
            assert f.target_component_id == "redis"


def test_store_save_and_load(tmp_path):
    store_path = tmp_path / "test-store.json"

    articles = [_make_article("DDoS attack floods network")]
    incidents = analyze_articles(articles)
    scenarios = incidents_to_scenarios(incidents, ["server-1"])

    save_feed_scenarios(scenarios, store_path=store_path)
    loaded = load_feed_scenarios(store_path=store_path)

    assert len(loaded) == len(scenarios)
    assert loaded[0].name == scenarios[0].name


def test_store_merge_deduplicates(tmp_path):
    store_path = tmp_path / "test-store.json"

    articles = [_make_article("DDoS attack")]
    incidents = analyze_articles(articles)
    scenarios = incidents_to_scenarios(incidents, ["server-1"])

    # Save twice - should deduplicate
    save_feed_scenarios(scenarios, store_path=store_path)
    save_feed_scenarios(scenarios, store_path=store_path)

    loaded = load_feed_scenarios(store_path=store_path)
    assert len(loaded) == len(scenarios)  # Not doubled


def test_store_clear(tmp_path):
    store_path = tmp_path / "test-store.json"

    articles = [_make_article("DDoS attack")]
    incidents = analyze_articles(articles)
    scenarios = incidents_to_scenarios(incidents, ["server-1"])
    save_feed_scenarios(scenarios, store_path=store_path)

    clear_store(store_path=store_path)
    loaded = load_feed_scenarios(store_path=store_path)
    assert len(loaded) == 0


def test_confidence_scoring():
    # Article with many keyword matches should have higher confidence
    high_match = _make_article(
        "Massive DDoS denial of service HTTP flood volumetric attack"
    )
    low_match = _make_article("Possible denial of service risk")

    high_incidents = analyze_articles([high_match])
    low_incidents = analyze_articles([low_match])

    assert len(high_incidents) > 0
    assert len(low_incidents) > 0
    assert high_incidents[0].confidence >= low_incidents[0].confidence
