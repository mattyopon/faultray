"""Tests for the Chaos Scenario Marketplace (v2 package system)."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from faultray.marketplace.catalog import (
    CATEGORIES,
    MarketplaceCategory,
    ScenarioMarketplace,
    ScenarioPackage,
    ScenarioReview,
)
from faultray.marketplace.builtin_packages import BUILTIN_PACKAGES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_package(
    pkg_id: str = "test-pkg-001",
    name: str = "Test Package",
    category: str = "infrastructure",
    provider: str = "aws",
    severity: str = "high",
    difficulty: str = "intermediate",
    scenarios: list[dict] | None = None,
    featured: bool = False,
    downloads: int = 0,
    rating: float = 0.0,
) -> ScenarioPackage:
    if scenarios is None:
        scenarios = [
            {
                "name": "Test Scenario 1",
                "description": "A simple test scenario",
                "faults": [
                    {
                        "target_component_id": "app-server-1",
                        "fault_type": "component_down",
                        "severity": 1.0,
                        "duration_seconds": 300,
                        "_required_type": "app_server",
                    },
                ],
                "traffic_multiplier": 1.0,
            },
        ]

    return ScenarioPackage(
        id=pkg_id,
        name=name,
        version="1.0.0",
        description="A test chaos scenario package",
        author="tester",
        category=category,
        provider=provider,
        severity=severity,
        tags=["test", "chaos"],
        scenarios=scenarios,
        prerequisites=["app_server"],
        estimated_duration="30min",
        difficulty=difficulty,
        downloads=downloads,
        rating=rating,
        featured=featured,
    )


# ---------------------------------------------------------------------------
# ScenarioReview tests
# ---------------------------------------------------------------------------


class TestScenarioReview:
    def test_review_creation(self):
        r = ScenarioReview(author="alice", rating=5, comment="Great!")
        assert r.author == "alice"
        assert r.rating == 5
        assert isinstance(r.date, datetime)

    def test_review_to_dict_roundtrip(self):
        r = ScenarioReview(author="bob", rating=3, comment="Okay")
        d = r.to_dict()
        restored = ScenarioReview.from_dict(d)
        assert restored.author == "bob"
        assert restored.rating == 3
        assert restored.comment == "Okay"

    def test_review_from_dict_with_missing_date(self):
        r = ScenarioReview.from_dict({"author": "carol", "rating": 4})
        assert r.author == "carol"
        assert r.rating == 4
        assert isinstance(r.date, datetime)

    def test_review_from_dict_with_invalid_date_string(self):
        """Line 89-90: Invalid date string falls back to datetime.now()."""
        r = ScenarioReview.from_dict({
            "author": "dave",
            "rating": 3,
            "date": "not-a-valid-date",
        })
        assert r.author == "dave"
        assert isinstance(r.date, datetime)

    def test_review_from_dict_with_non_string_non_datetime_date(self):
        """Line 91-92: Non-string, non-datetime date value falls back."""
        r = ScenarioReview.from_dict({
            "author": "eve",
            "rating": 2,
            "date": 12345,
        })
        assert r.author == "eve"
        assert isinstance(r.date, datetime)


# ---------------------------------------------------------------------------
# ScenarioPackage tests
# ---------------------------------------------------------------------------


class TestScenarioPackage:
    def test_package_creation(self):
        pkg = _make_package()
        assert pkg.id == "test-pkg-001"
        assert pkg.name == "Test Package"
        assert pkg.scenario_count == 1

    def test_average_rating_no_reviews(self):
        pkg = _make_package(rating=4.5)
        assert pkg.average_rating == 4.5

    def test_average_rating_with_reviews(self):
        pkg = _make_package(rating=0.0)
        pkg.reviews = [
            ScenarioReview(author="a", rating=5, comment=""),
            ScenarioReview(author="b", rating=3, comment=""),
        ]
        assert pkg.average_rating == 4.0

    def test_to_dict_from_dict_roundtrip(self):
        pkg = _make_package(downloads=42, rating=4.2, featured=True)
        d = pkg.to_dict()
        restored = ScenarioPackage.from_dict(d)
        assert restored.id == pkg.id
        assert restored.name == pkg.name
        assert restored.downloads == 42
        assert restored.rating == 4.2
        assert restored.featured is True
        assert restored.scenario_count == pkg.scenario_count

    def test_to_dict_contains_all_fields(self):
        pkg = _make_package()
        d = pkg.to_dict()
        required_keys = {
            "id", "name", "version", "description", "author", "category",
            "provider", "severity", "tags", "scenarios", "prerequisites",
            "estimated_duration", "difficulty", "created_at", "updated_at",
            "downloads", "rating", "reviews", "featured",
        }
        assert required_keys.issubset(d.keys())

    def test_from_dict_with_invalid_datetime_string(self):
        """Line 164-165: Invalid datetime string falls back to now()."""
        pkg = _make_package()
        d = pkg.to_dict()
        d["created_at"] = "not-a-valid-datetime"
        d["updated_at"] = "also-invalid"
        restored = ScenarioPackage.from_dict(d)
        assert isinstance(restored.created_at, datetime)
        assert isinstance(restored.updated_at, datetime)

    def test_from_dict_with_numeric_datetime(self):
        """Line 166-168: Non-string, non-datetime value falls back to now()."""
        pkg = _make_package()
        d = pkg.to_dict()
        d["created_at"] = 12345
        d["updated_at"] = None
        restored = ScenarioPackage.from_dict(d)
        assert isinstance(restored.created_at, datetime)
        assert isinstance(restored.updated_at, datetime)

    def test_from_dict_with_datetime_object(self):
        """Line 167: datetime object passed directly should be kept as-is."""
        pkg = _make_package()
        d = pkg.to_dict()
        fixed_dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        d["created_at"] = fixed_dt
        restored = ScenarioPackage.from_dict(d)
        assert restored.created_at == fixed_dt


# ---------------------------------------------------------------------------
# MarketplaceCategory tests
# ---------------------------------------------------------------------------


class TestMarketplaceCategory:
    def test_category_creation(self):
        cat = MarketplaceCategory(
            name="test",
            display_name="Test",
            description="A test category",
            icon="T",
        )
        assert cat.name == "test"
        assert cat.package_count == 0

    def test_to_dict(self):
        cat = MarketplaceCategory(
            name="security",
            display_name="Security",
            description="Security scenarios",
            icon="S",
            package_count=5,
        )
        d = cat.to_dict()
        assert d["name"] == "security"
        assert d["package_count"] == 5

    def test_default_categories_exist(self):
        names = [c.name for c in CATEGORIES]
        assert "infrastructure" in names
        assert "security" in names
        assert "compliance" in names
        assert "performance" in names
        assert "disaster_recovery" in names


# ---------------------------------------------------------------------------
# Built-in packages tests
# ---------------------------------------------------------------------------


class TestBuiltinPackages:
    def test_at_least_15_packages(self):
        assert len(BUILTIN_PACKAGES) >= 15

    def test_all_packages_have_scenarios(self):
        for pkg in BUILTIN_PACKAGES:
            assert len(pkg.scenarios) >= 3, f"Package {pkg.id} has < 3 scenarios"

    def test_all_packages_have_valid_category(self):
        valid = {"infrastructure", "security", "compliance", "performance", "disaster_recovery"}
        for pkg in BUILTIN_PACKAGES:
            assert pkg.category in valid, f"Package {pkg.id} has invalid category: {pkg.category}"

    def test_all_packages_have_valid_provider(self):
        valid = {"aws", "azure", "gcp", "kubernetes", "generic"}
        for pkg in BUILTIN_PACKAGES:
            assert pkg.provider in valid, f"Package {pkg.id} has invalid provider: {pkg.provider}"

    def test_all_packages_have_valid_severity(self):
        valid = {"critical", "high", "medium", "low"}
        for pkg in BUILTIN_PACKAGES:
            assert pkg.severity in valid, f"Package {pkg.id} has invalid severity: {pkg.severity}"

    def test_all_packages_have_valid_difficulty(self):
        valid = {"beginner", "intermediate", "advanced", "expert"}
        for pkg in BUILTIN_PACKAGES:
            assert pkg.difficulty in valid, f"Package {pkg.id} has invalid difficulty: {pkg.difficulty}"

    def test_unique_package_ids(self):
        ids = [pkg.id for pkg in BUILTIN_PACKAGES]
        assert len(ids) == len(set(ids)), "Duplicate package IDs found"

    def test_some_packages_are_featured(self):
        featured = [pkg for pkg in BUILTIN_PACKAGES if pkg.featured]
        assert len(featured) >= 3, "At least 3 featured packages expected"

    def test_scenarios_have_faults(self):
        for pkg in BUILTIN_PACKAGES:
            for s in pkg.scenarios:
                assert len(s.get("faults", [])) >= 1, (
                    f"Scenario '{s.get('name', '?')}' in {pkg.id} has no faults"
                )

    def test_scenarios_have_valid_fault_types(self):
        from faultray.simulator.scenarios import FaultType

        valid_types = {ft.value for ft in FaultType}
        for pkg in BUILTIN_PACKAGES:
            for s in pkg.scenarios:
                for f in s.get("faults", []):
                    assert f["fault_type"] in valid_types, (
                        f"Invalid fault_type '{f['fault_type']}' in {pkg.id}/{s.get('name')}"
                    )


# ---------------------------------------------------------------------------
# ScenarioMarketplace tests
# ---------------------------------------------------------------------------


class TestScenarioMarketplace:
    @pytest.fixture()
    def mp(self, tmp_path: Path) -> ScenarioMarketplace:
        return ScenarioMarketplace(store_path=tmp_path / "marketplace")

    def test_list_all_packages_includes_builtins(self, mp: ScenarioMarketplace):
        packages = mp.list_packages()
        assert len(packages) >= 15  # At least all built-ins

    def test_list_packages_filter_by_category(self, mp: ScenarioMarketplace):
        dr_packages = mp.list_packages(category="disaster_recovery")
        assert all(p.category == "disaster_recovery" for p in dr_packages)
        assert len(dr_packages) >= 1

    def test_list_packages_filter_by_provider(self, mp: ScenarioMarketplace):
        aws_packages = mp.list_packages(provider="aws")
        assert all(p.provider == "aws" for p in aws_packages)
        assert len(aws_packages) >= 1

    def test_list_packages_filter_both(self, mp: ScenarioMarketplace):
        packages = mp.list_packages(category="infrastructure", provider="kubernetes")
        assert all(
            p.category == "infrastructure" and p.provider == "kubernetes"
            for p in packages
        )

    def test_search_by_keyword(self, mp: ScenarioMarketplace):
        results = mp.search("kubernetes")
        assert len(results) >= 1
        assert any("kubernetes" in r.name.lower() or "kubernetes" in " ".join(r.tags) for r in results)

    def test_search_no_results(self, mp: ScenarioMarketplace):
        results = mp.search("nonexistent_xyz_query_12345")
        assert len(results) == 0

    def test_get_package_builtin(self, mp: ScenarioMarketplace):
        pkg = mp.get_package("aws-region-failover")
        assert pkg.name == "AWS Region Failover Suite"

    def test_get_package_not_found(self, mp: ScenarioMarketplace):
        with pytest.raises(KeyError, match="not found"):
            mp.get_package("nonexistent-pkg")

    def test_install_package(self, mp: ScenarioMarketplace):
        scenarios = mp.install_package("gameday-starter-kit")
        assert len(scenarios) >= 3
        for s in scenarios:
            assert s.id.startswith("marketplace-gameday-starter-kit-")
            assert len(s.faults) >= 1

    def test_install_increments_downloads(self, mp: ScenarioMarketplace):
        original = mp.get_package("gameday-starter-kit")
        original_downloads = original.downloads
        mp.install_package("gameday-starter-kit")
        # The package should now be saved in user store with incremented downloads
        pkg = mp.get_package("gameday-starter-kit")
        assert pkg.downloads == original_downloads + 1

    def test_install_not_found(self, mp: ScenarioMarketplace):
        with pytest.raises(KeyError):
            mp.install_package("nonexistent-pkg")

    def test_export_scenarios(self, mp: ScenarioMarketplace):
        from faultray.simulator.scenarios import Fault, FaultType, Scenario

        scenarios = [
            Scenario(
                id="s1",
                name="Test Scenario",
                description="A test",
                faults=[
                    Fault(
                        target_component_id="t1",
                        fault_type=FaultType.COMPONENT_DOWN,
                        severity=1.0,
                    ),
                ],
            ),
        ]
        pkg = mp.export_scenarios(scenarios, package_name="My Test Pack")
        assert pkg.id == "my-test-pack"
        assert pkg.name == "My Test Pack"
        assert len(pkg.scenarios) == 1

        # Verify it was saved
        saved = mp.get_package("my-test-pack")
        assert saved.name == "My Test Pack"

    def test_get_categories(self, mp: ScenarioMarketplace):
        categories = mp.get_categories()
        assert len(categories) >= 5
        names = [c.name for c in categories]
        assert "infrastructure" in names
        # At least some categories should have packages
        infra = next(c for c in categories if c.name == "infrastructure")
        assert infra.package_count > 0

    def test_get_featured(self, mp: ScenarioMarketplace):
        featured = mp.get_featured()
        assert len(featured) >= 3
        assert all(p.featured for p in featured)

    def test_get_popular(self, mp: ScenarioMarketplace):
        popular = mp.get_popular()
        assert len(popular) >= 1
        # Should be sorted by downloads descending
        for i in range(len(popular) - 1):
            assert popular[i].downloads >= popular[i + 1].downloads

    def test_get_new(self, mp: ScenarioMarketplace):
        new_pkgs = mp.get_new()
        assert len(new_pkgs) >= 1
        # Should be sorted by created_at descending
        for i in range(len(new_pkgs) - 1):
            assert new_pkgs[i].created_at >= new_pkgs[i + 1].created_at

    def test_add_review(self, mp: ScenarioMarketplace):
        # Install a package first so it's in user store
        mp.install_package("gameday-starter-kit")
        mp.add_review("gameday-starter-kit", author="alice", rating=5, comment="Great!")
        pkg = mp.get_package("gameday-starter-kit")
        assert len(pkg.reviews) >= 1
        alice_review = next(r for r in pkg.reviews if r.author == "alice")
        assert alice_review.rating == 5

    def test_add_review_update_existing(self, mp: ScenarioMarketplace):
        mp.install_package("gameday-starter-kit")
        mp.add_review("gameday-starter-kit", author="alice", rating=3, comment="OK")
        mp.add_review("gameday-starter-kit", author="alice", rating=5, comment="Updated!")
        pkg = mp.get_package("gameday-starter-kit")
        alice_reviews = [r for r in pkg.reviews if r.author == "alice"]
        assert len(alice_reviews) == 1
        assert alice_reviews[0].rating == 5

    def test_add_review_invalid_score(self, mp: ScenarioMarketplace):
        mp.install_package("gameday-starter-kit")
        with pytest.raises(ValueError, match="between 1 and 5"):
            mp.add_review("gameday-starter-kit", author="bob", rating=0)
        with pytest.raises(ValueError, match="between 1 and 5"):
            mp.add_review("gameday-starter-kit", author="bob", rating=6)

    def test_user_package_overrides_builtin(self, mp: ScenarioMarketplace):
        """User-installed package with same ID should override built-in."""
        custom_pkg = _make_package(
            pkg_id="gameday-starter-kit",
            name="Custom GameDay Kit",
            downloads=999,
        )
        # Write directly to the store
        path = mp._store / "gameday-starter-kit.json"
        path.write_text(json.dumps(custom_pkg.to_dict(), default=str), encoding="utf-8")

        pkg = mp.get_package("gameday-starter-kit")
        assert pkg.name == "Custom GameDay Kit"
        assert pkg.downloads == 999

    def test_installed_scenarios_have_correct_fault_types(self, mp: ScenarioMarketplace):
        from faultray.simulator.scenarios import FaultType

        scenarios = mp.install_package("aws-database-chaos")
        for s in scenarios:
            for f in s.faults:
                assert isinstance(f.fault_type, FaultType)

    def test_load_user_package_with_invalid_json(self, mp: ScenarioMarketplace):
        """Line 301-302: Invalid JSON in user store is silently skipped."""
        # Write an invalid JSON file to the store
        bad_path = mp._store / "broken-pkg.json"
        bad_path.write_text("{not valid json!!!", encoding="utf-8")
        # Should not raise, just skip the bad file
        packages = mp.list_packages()
        assert all(p.id != "broken-pkg" for p in packages)

    def test_install_package_with_invalid_fault_type(self, mp: ScenarioMarketplace):
        """Line 372-373: Invalid fault_type in scenario data falls back
        to COMPONENT_DOWN."""
        from faultray.simulator.scenarios import FaultType

        custom_pkg = _make_package(
            pkg_id="bad-fault-pkg",
            name="Bad Fault Package",
            scenarios=[
                {
                    "name": "Bad Fault Scenario",
                    "description": "Has an invalid fault type",
                    "faults": [
                        {
                            "target_component_id": "app-1",
                            "fault_type": "totally_invalid_fault_type",
                            "severity": 1.0,
                            "duration_seconds": 300,
                        },
                    ],
                    "traffic_multiplier": 1.0,
                },
            ],
        )
        # Write the package to the store
        path = mp._store / "bad-fault-pkg.json"
        path.write_text(
            json.dumps(custom_pkg.to_dict(), default=str), encoding="utf-8"
        )

        scenarios = mp.install_package("bad-fault-pkg")
        assert len(scenarios) == 1
        assert scenarios[0].faults[0].fault_type == FaultType.COMPONENT_DOWN


# ---------------------------------------------------------------------------
# Integration: marketplace + scenario model
# ---------------------------------------------------------------------------


class TestMarketplaceBuiltinLoadFailure:
    def test_builtin_import_failure_graceful(self, tmp_path: Path):
        """Line 281-283: If builtin_packages fails to import, marketplace
        should still work with an empty builtin list."""
        import unittest.mock as mock

        # Patch the import inside _load_builtins to raise an exception
        with mock.patch.dict(
            "sys.modules",
            {"faultray.marketplace.builtin_packages": None},
        ):
            # Force fresh instance that will try to import and fail
            mp = ScenarioMarketplace.__new__(ScenarioMarketplace)
            mp._store = tmp_path / "marketplace"
            mp._store.mkdir(parents=True, exist_ok=True)
            mp._builtin = []
            mp._load_builtins()
            # After failure, _builtin should be empty
            assert mp._builtin == []


class TestMarketplaceIntegration:
    @pytest.fixture()
    def mp(self, tmp_path: Path) -> ScenarioMarketplace:
        return ScenarioMarketplace(store_path=tmp_path / "marketplace")

    def test_installed_scenarios_are_valid(self, mp: ScenarioMarketplace):
        """All installed scenarios should be valid Scenario objects."""
        from faultray.simulator.scenarios import Scenario

        for builtin in BUILTIN_PACKAGES[:5]:  # Test first 5 for speed
            scenarios = mp.install_package(builtin.id)
            for s in scenarios:
                assert isinstance(s, Scenario)
                assert s.id.startswith("marketplace-")
                assert len(s.faults) >= 1
                assert s.traffic_multiplier >= 0

    def test_package_json_serialization(self, mp: ScenarioMarketplace):
        """Packages should roundtrip through JSON cleanly."""
        for pkg in BUILTIN_PACKAGES:
            d = pkg.to_dict()
            json_str = json.dumps(d, default=str)
            restored_data = json.loads(json_str)
            restored = ScenarioPackage.from_dict(restored_data)
            assert restored.id == pkg.id
            assert restored.scenario_count == pkg.scenario_count
