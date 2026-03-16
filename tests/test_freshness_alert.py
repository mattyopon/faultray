"""Tests for Dependency Freshness Alerting engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from faultray.simulator.freshness_alert import (
    FreshnessAlert,
    FreshnessAlertEngine,
    FreshnessCategory,
    FreshnessLevel,
    FreshnessPolicy,
    FreshnessRecord,
    FreshnessReport,
    _DEFAULT_MAX_AGE,
    _LEVEL_SCORES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _days_ago(days: float) -> datetime:
    return _now() - timedelta(days=days)


def _make_record(
    component_id: str = "web-1",
    category: FreshnessCategory = FreshnessCategory.SOFTWARE_VERSION,
    item_name: str = "nginx",
    current_version: str = "1.24",
    latest_version: str | None = "1.27",
    days_old: float = 0,
    max_age_days: int | None = None,
    freshness_level: FreshnessLevel | None = None,
) -> FreshnessRecord:
    if max_age_days is None:
        max_age_days = _DEFAULT_MAX_AGE[category]
    return FreshnessRecord(
        component_id=component_id,
        category=category,
        item_name=item_name,
        current_version=current_version,
        latest_version=latest_version,
        last_updated=_days_ago(days_old),
        max_age_days=max_age_days,
        freshness_level=freshness_level,
    )


def _engine_with(*records: FreshnessRecord) -> FreshnessAlertEngine:
    engine = FreshnessAlertEngine()
    for r in records:
        engine.add_record(r)
    return engine


# =========================================================================
# 1. Enum tests
# =========================================================================


class TestFreshnessCategoryEnum:
    def test_all_categories_present(self):
        expected = {
            "SOFTWARE_VERSION",
            "CERTIFICATE",
            "CONFIGURATION",
            "PATCH_LEVEL",
            "DEPENDENCY_VERSION",
            "BACKUP",
            "DOCUMENTATION",
            "RUNBOOK",
        }
        assert {c.name for c in FreshnessCategory} == expected

    def test_category_values(self):
        assert FreshnessCategory.SOFTWARE_VERSION.value == "software_version"
        assert FreshnessCategory.CERTIFICATE.value == "certificate"
        assert FreshnessCategory.CONFIGURATION.value == "configuration"
        assert FreshnessCategory.PATCH_LEVEL.value == "patch_level"
        assert FreshnessCategory.DEPENDENCY_VERSION.value == "dependency_version"
        assert FreshnessCategory.BACKUP.value == "backup"
        assert FreshnessCategory.DOCUMENTATION.value == "documentation"
        assert FreshnessCategory.RUNBOOK.value == "runbook"

    def test_category_count(self):
        assert len(FreshnessCategory) == 8

    def test_category_is_string_enum(self):
        assert isinstance(FreshnessCategory.BACKUP, str)


class TestFreshnessLevelEnum:
    def test_all_levels_present(self):
        expected = {"CURRENT", "AGING", "STALE", "CRITICAL", "EXPIRED"}
        assert {lv.name for lv in FreshnessLevel} == expected

    def test_level_values(self):
        assert FreshnessLevel.CURRENT.value == "current"
        assert FreshnessLevel.AGING.value == "aging"
        assert FreshnessLevel.STALE.value == "stale"
        assert FreshnessLevel.CRITICAL.value == "critical"
        assert FreshnessLevel.EXPIRED.value == "expired"

    def test_level_count(self):
        assert len(FreshnessLevel) == 5

    def test_level_is_string_enum(self):
        assert isinstance(FreshnessLevel.CURRENT, str)


# =========================================================================
# 2. Pydantic model tests
# =========================================================================


class TestFreshnessRecord:
    def test_basic_creation(self):
        rec = _make_record()
        assert rec.component_id == "web-1"
        assert rec.category == FreshnessCategory.SOFTWARE_VERSION
        assert rec.item_name == "nginx"
        assert rec.current_version == "1.24"
        assert rec.latest_version == "1.27"
        assert rec.max_age_days == 180
        assert rec.freshness_level is None

    def test_latest_version_optional(self):
        rec = _make_record(latest_version=None)
        assert rec.latest_version is None

    def test_freshness_level_default_none(self):
        rec = _make_record()
        assert rec.freshness_level is None

    def test_freshness_level_settable(self):
        rec = _make_record(freshness_level=FreshnessLevel.STALE)
        assert rec.freshness_level == FreshnessLevel.STALE

    def test_all_categories_accepted(self):
        for cat in FreshnessCategory:
            rec = _make_record(category=cat)
            assert rec.category == cat

    def test_max_age_days_positive(self):
        rec = _make_record(max_age_days=1)
        assert rec.max_age_days == 1


class TestFreshnessAlert:
    def test_creation(self):
        rec = _make_record(days_old=100)
        alert = FreshnessAlert(
            record=rec,
            age_days=100.0,
            overdue_days=0.0,
            risk_score=0.5,
            recommendation="Update soon.",
        )
        assert alert.age_days == 100.0
        assert alert.overdue_days == 0.0
        assert alert.risk_score == 0.5
        assert alert.recommendation == "Update soon."

    def test_risk_score_bounds_lower(self):
        rec = _make_record()
        alert = FreshnessAlert(
            record=rec, age_days=0, overdue_days=0, risk_score=0.0,
            recommendation="ok",
        )
        assert alert.risk_score == 0.0

    def test_risk_score_bounds_upper(self):
        rec = _make_record()
        alert = FreshnessAlert(
            record=rec, age_days=0, overdue_days=0, risk_score=1.0,
            recommendation="ok",
        )
        assert alert.risk_score == 1.0

    def test_risk_score_rejects_over_one(self):
        rec = _make_record()
        with pytest.raises(Exception):
            FreshnessAlert(
                record=rec, age_days=0, overdue_days=0, risk_score=1.1,
                recommendation="ok",
            )

    def test_risk_score_rejects_negative(self):
        rec = _make_record()
        with pytest.raises(Exception):
            FreshnessAlert(
                record=rec, age_days=0, overdue_days=0, risk_score=-0.1,
                recommendation="ok",
            )


class TestFreshnessPolicy:
    def test_defaults(self):
        pol = FreshnessPolicy(
            category=FreshnessCategory.BACKUP, max_age_days=7
        )
        assert pol.warning_at_percent == 75.0
        assert pol.critical_at_percent == 90.0

    def test_custom_percentages(self):
        pol = FreshnessPolicy(
            category=FreshnessCategory.CERTIFICATE,
            max_age_days=365,
            warning_at_percent=60.0,
            critical_at_percent=85.0,
        )
        assert pol.warning_at_percent == 60.0
        assert pol.critical_at_percent == 85.0


class TestFreshnessReport:
    def test_creation(self):
        rpt = FreshnessReport(
            total_items=5,
            current_count=3,
            aging_count=1,
            stale_count=1,
            critical_count=0,
            expired_count=0,
            alerts=[],
            overall_freshness_score=82.5,
            recommendations=["All good."],
        )
        assert rpt.total_items == 5
        assert rpt.current_count == 3
        assert rpt.overall_freshness_score == 82.5

    def test_score_bounds(self):
        with pytest.raises(Exception):
            FreshnessReport(
                total_items=0, current_count=0, aging_count=0,
                stale_count=0, critical_count=0, expired_count=0,
                alerts=[], overall_freshness_score=101.0,
                recommendations=[],
            )


# =========================================================================
# 3. Default policy tests
# =========================================================================


class TestDefaultPolicies:
    def test_eight_default_policies(self):
        engine = FreshnessAlertEngine()
        assert len(engine._policies) == 8

    def test_all_categories_have_default_policy(self):
        engine = FreshnessAlertEngine()
        for cat in FreshnessCategory:
            assert cat in engine._policies

    def test_software_version_default(self):
        engine = FreshnessAlertEngine()
        assert engine._policies[FreshnessCategory.SOFTWARE_VERSION].max_age_days == 180

    def test_certificate_default(self):
        engine = FreshnessAlertEngine()
        assert engine._policies[FreshnessCategory.CERTIFICATE].max_age_days == 365

    def test_configuration_default(self):
        engine = FreshnessAlertEngine()
        assert engine._policies[FreshnessCategory.CONFIGURATION].max_age_days == 90

    def test_patch_level_default(self):
        engine = FreshnessAlertEngine()
        assert engine._policies[FreshnessCategory.PATCH_LEVEL].max_age_days == 30

    def test_dependency_version_default(self):
        engine = FreshnessAlertEngine()
        assert engine._policies[FreshnessCategory.DEPENDENCY_VERSION].max_age_days == 120

    def test_backup_default(self):
        engine = FreshnessAlertEngine()
        assert engine._policies[FreshnessCategory.BACKUP].max_age_days == 7

    def test_documentation_default(self):
        engine = FreshnessAlertEngine()
        assert engine._policies[FreshnessCategory.DOCUMENTATION].max_age_days == 180

    def test_runbook_default(self):
        engine = FreshnessAlertEngine()
        assert engine._policies[FreshnessCategory.RUNBOOK].max_age_days == 90

    def test_default_warning_percent(self):
        engine = FreshnessAlertEngine()
        for pol in engine._policies.values():
            assert pol.warning_at_percent == 75.0

    def test_default_critical_percent(self):
        engine = FreshnessAlertEngine()
        for pol in engine._policies.values():
            assert pol.critical_at_percent == 90.0


# =========================================================================
# 4. evaluate_freshness tests
# =========================================================================


class TestEvaluateFreshness:
    """Tests for FreshnessAlertEngine.evaluate_freshness."""

    # --- CURRENT ---
    def test_current_brand_new(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=0)
        assert engine.evaluate_freshness(rec) == FreshnessLevel.CURRENT

    def test_current_well_within_threshold(self):
        engine = FreshnessAlertEngine()
        # SW default: 180 days, warning at 75% = 135 days
        rec = _make_record(days_old=50)
        assert engine.evaluate_freshness(rec) == FreshnessLevel.CURRENT

    def test_current_just_below_warning(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=134)  # < 135
        assert engine.evaluate_freshness(rec) == FreshnessLevel.CURRENT

    # --- AGING ---
    def test_aging_at_warning_boundary(self):
        engine = FreshnessAlertEngine()
        # At exactly 135 days (75% of 180): age >= warning => AGING
        rec = _make_record(days_old=135)
        assert engine.evaluate_freshness(rec) == FreshnessLevel.AGING

    def test_aging_midrange(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=150)  # between 135 and 162
        assert engine.evaluate_freshness(rec) == FreshnessLevel.AGING

    def test_aging_just_below_critical(self):
        engine = FreshnessAlertEngine()
        # critical threshold = 90% of 180 = 162
        rec = _make_record(days_old=161)
        assert engine.evaluate_freshness(rec) == FreshnessLevel.AGING

    # --- STALE ---
    def test_stale_at_critical_boundary(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=162)  # = 90% of 180
        assert engine.evaluate_freshness(rec) == FreshnessLevel.STALE

    def test_stale_midrange(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=170)
        assert engine.evaluate_freshness(rec) == FreshnessLevel.STALE

    def test_stale_just_below_max_age(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=179)
        assert engine.evaluate_freshness(rec) == FreshnessLevel.STALE

    # --- CRITICAL ---
    def test_critical_at_max_age(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=180)  # = max_age exactly
        assert engine.evaluate_freshness(rec) == FreshnessLevel.CRITICAL

    def test_critical_midrange(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=220)  # between 180 and 270
        assert engine.evaluate_freshness(rec) == FreshnessLevel.CRITICAL

    def test_critical_just_below_expired(self):
        engine = FreshnessAlertEngine()
        # expired = 180 * 1.5 = 270
        rec = _make_record(days_old=269)
        assert engine.evaluate_freshness(rec) == FreshnessLevel.CRITICAL

    # --- EXPIRED ---
    def test_expired_at_boundary(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=270)  # = 180 * 1.5
        assert engine.evaluate_freshness(rec) == FreshnessLevel.EXPIRED

    def test_expired_well_past(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=500)
        assert engine.evaluate_freshness(rec) == FreshnessLevel.EXPIRED

    # --- Category-specific defaults ---
    def test_backup_current_within_7_days(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(category=FreshnessCategory.BACKUP, days_old=3)
        assert engine.evaluate_freshness(rec) == FreshnessLevel.CURRENT

    def test_backup_expired_after_10_5_days(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(category=FreshnessCategory.BACKUP, days_old=11)
        assert engine.evaluate_freshness(rec) == FreshnessLevel.EXPIRED

    def test_certificate_current_within_a_year(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(
            category=FreshnessCategory.CERTIFICATE, days_old=200
        )
        assert engine.evaluate_freshness(rec) == FreshnessLevel.CURRENT

    def test_patch_level_stale(self):
        engine = FreshnessAlertEngine()
        # patch: 30 days max, warning 75%=22.5, critical 90%=27
        rec = _make_record(category=FreshnessCategory.PATCH_LEVEL, days_old=28)
        assert engine.evaluate_freshness(rec) == FreshnessLevel.STALE

    def test_patch_level_critical(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(category=FreshnessCategory.PATCH_LEVEL, days_old=35)
        assert engine.evaluate_freshness(rec) == FreshnessLevel.CRITICAL

    def test_configuration_aging(self):
        engine = FreshnessAlertEngine()
        # config: 90 days, warning at 67.5
        rec = _make_record(
            category=FreshnessCategory.CONFIGURATION, days_old=70
        )
        assert engine.evaluate_freshness(rec) == FreshnessLevel.AGING

    def test_dependency_version_stale(self):
        engine = FreshnessAlertEngine()
        # dep version: 120 days, critical at 108
        rec = _make_record(
            category=FreshnessCategory.DEPENDENCY_VERSION, days_old=115
        )
        assert engine.evaluate_freshness(rec) == FreshnessLevel.STALE

    def test_documentation_current(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(
            category=FreshnessCategory.DOCUMENTATION, days_old=10
        )
        assert engine.evaluate_freshness(rec) == FreshnessLevel.CURRENT

    def test_runbook_expired(self):
        engine = FreshnessAlertEngine()
        # runbook: 90 days, expired at 135
        rec = _make_record(
            category=FreshnessCategory.RUNBOOK, days_old=140
        )
        assert engine.evaluate_freshness(rec) == FreshnessLevel.EXPIRED

    # --- Custom policy ---
    def test_custom_policy_changes_thresholds(self):
        engine = FreshnessAlertEngine()
        engine.set_policy(FreshnessPolicy(
            category=FreshnessCategory.SOFTWARE_VERSION,
            max_age_days=30,
            warning_at_percent=50.0,
            critical_at_percent=80.0,
        ))
        rec = _make_record(
            category=FreshnessCategory.SOFTWARE_VERSION, days_old=20
        )
        # warning at 50% of 30 = 15, critical at 80% of 30 = 24
        # 20 days => between 15 and 24 => AGING
        assert engine.evaluate_freshness(rec) == FreshnessLevel.AGING

    def test_custom_policy_expired(self):
        engine = FreshnessAlertEngine()
        engine.set_policy(FreshnessPolicy(
            category=FreshnessCategory.BACKUP,
            max_age_days=1,
        ))
        rec = _make_record(category=FreshnessCategory.BACKUP, days_old=2)
        # expired threshold = 1 * 1.5 = 1.5 => 2 >= 1.5 => EXPIRED
        assert engine.evaluate_freshness(rec) == FreshnessLevel.EXPIRED

    def test_custom_policy_current(self):
        engine = FreshnessAlertEngine()
        engine.set_policy(FreshnessPolicy(
            category=FreshnessCategory.CERTIFICATE,
            max_age_days=730,
            warning_at_percent=80.0,
            critical_at_percent=95.0,
        ))
        rec = _make_record(
            category=FreshnessCategory.CERTIFICATE, days_old=500
        )
        # warning at 80% of 730 = 584, 500 < 584 => CURRENT
        assert engine.evaluate_freshness(rec) == FreshnessLevel.CURRENT


class TestEvaluateFreshnessEdgeCases:
    def test_zero_age(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=0)
        assert engine.evaluate_freshness(rec) == FreshnessLevel.CURRENT

    def test_naive_datetime_handled(self):
        """Records with naive (no tzinfo) datetimes should still work."""
        engine = FreshnessAlertEngine()
        rec = FreshnessRecord(
            component_id="x",
            category=FreshnessCategory.BACKUP,
            item_name="db-backup",
            current_version="v1",
            last_updated=datetime.now() - timedelta(days=1),  # naive
            max_age_days=7,
        )
        level = engine.evaluate_freshness(rec)
        assert level == FreshnessLevel.CURRENT

    def test_very_old_record(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=10000)
        assert engine.evaluate_freshness(rec) == FreshnessLevel.EXPIRED

    def test_fractional_day_old(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=0.5)
        assert engine.evaluate_freshness(rec) == FreshnessLevel.CURRENT

    def test_no_policy_for_category_uses_defaults(self):
        """When the policy dict has no entry for the category, fallback
        warning_pct=75 and critical_pct=90 are used."""
        engine = FreshnessAlertEngine()
        # Remove the policy for SOFTWARE_VERSION
        del engine._policies[FreshnessCategory.SOFTWARE_VERSION]
        # Record max_age_days=100, warning=75 => 75, critical=90 => 90
        rec = _make_record(
            category=FreshnessCategory.SOFTWARE_VERSION,
            max_age_days=100,
            days_old=80,  # between 75 (warning) and 90 (critical) => AGING
        )
        assert engine.evaluate_freshness(rec) == FreshnessLevel.AGING

    def test_no_policy_current(self):
        """Fallback path: age below 75% of max_age => CURRENT."""
        engine = FreshnessAlertEngine()
        del engine._policies[FreshnessCategory.CONFIGURATION]
        rec = _make_record(
            category=FreshnessCategory.CONFIGURATION,
            max_age_days=100,
            days_old=50,  # < 75 => CURRENT
        )
        assert engine.evaluate_freshness(rec) == FreshnessLevel.CURRENT


# =========================================================================
# 5. add_record tests
# =========================================================================


class TestAddRecord:
    def test_adds_single_record(self):
        engine = FreshnessAlertEngine()
        engine.add_record(_make_record())
        assert len(engine._records) == 1

    def test_adds_multiple_records(self):
        engine = FreshnessAlertEngine()
        for i in range(5):
            engine.add_record(_make_record(component_id=f"c-{i}"))
        assert len(engine._records) == 5

    def test_duplicate_records_allowed(self):
        engine = FreshnessAlertEngine()
        rec = _make_record()
        engine.add_record(rec)
        engine.add_record(rec)
        assert len(engine._records) == 2


# =========================================================================
# 6. set_policy tests
# =========================================================================


class TestSetPolicy:
    def test_overrides_default(self):
        engine = FreshnessAlertEngine()
        assert engine._policies[FreshnessCategory.BACKUP].max_age_days == 7
        engine.set_policy(FreshnessPolicy(
            category=FreshnessCategory.BACKUP, max_age_days=14
        ))
        assert engine._policies[FreshnessCategory.BACKUP].max_age_days == 14

    def test_preserves_other_policies(self):
        engine = FreshnessAlertEngine()
        engine.set_policy(FreshnessPolicy(
            category=FreshnessCategory.BACKUP, max_age_days=14
        ))
        assert engine._policies[FreshnessCategory.SOFTWARE_VERSION].max_age_days == 180

    def test_set_policy_multiple_times(self):
        engine = FreshnessAlertEngine()
        engine.set_policy(FreshnessPolicy(
            category=FreshnessCategory.BACKUP, max_age_days=14
        ))
        engine.set_policy(FreshnessPolicy(
            category=FreshnessCategory.BACKUP, max_age_days=21
        ))
        assert engine._policies[FreshnessCategory.BACKUP].max_age_days == 21


# =========================================================================
# 7. generate_alerts tests
# =========================================================================


class TestGenerateAlerts:
    def test_no_records_no_alerts(self):
        engine = FreshnessAlertEngine()
        assert engine.generate_alerts() == []

    def test_current_record_no_alert(self):
        engine = _engine_with(_make_record(days_old=10))
        alerts = engine.generate_alerts()
        assert len(alerts) == 0

    def test_aging_record_no_alert(self):
        engine = _engine_with(_make_record(days_old=140))
        alerts = engine.generate_alerts()
        assert len(alerts) == 0

    def test_stale_record_generates_alert(self):
        engine = _engine_with(_make_record(days_old=165))
        alerts = engine.generate_alerts()
        assert len(alerts) == 1
        assert "WARNING" in alerts[0].recommendation

    def test_critical_record_generates_alert(self):
        engine = _engine_with(_make_record(days_old=200))
        alerts = engine.generate_alerts()
        assert len(alerts) == 1
        assert "CRITICAL" in alerts[0].recommendation

    def test_expired_record_generates_alert(self):
        engine = _engine_with(_make_record(days_old=300))
        alerts = engine.generate_alerts()
        assert len(alerts) == 1
        assert "URGENT" in alerts[0].recommendation

    def test_multiple_alerts_sorted_by_risk(self):
        engine = _engine_with(
            _make_record(component_id="a", days_old=165),  # stale
            _make_record(component_id="b", days_old=300),  # expired
            _make_record(component_id="c", days_old=200),  # critical
        )
        alerts = engine.generate_alerts()
        assert len(alerts) == 3
        # Sorted descending by risk_score
        assert alerts[0].risk_score >= alerts[1].risk_score
        assert alerts[1].risk_score >= alerts[2].risk_score

    def test_mix_of_alerting_and_non_alerting(self):
        engine = _engine_with(
            _make_record(component_id="fresh", days_old=10),  # CURRENT
            _make_record(component_id="old", days_old=300),   # EXPIRED
        )
        alerts = engine.generate_alerts()
        assert len(alerts) == 1
        assert alerts[0].record.component_id == "old"

    def test_alert_overdue_days_positive_for_expired(self):
        engine = _engine_with(_make_record(days_old=300))
        alerts = engine.generate_alerts()
        assert alerts[0].overdue_days > 0

    def test_alert_overdue_days_zero_for_stale_within_max(self):
        engine = _engine_with(_make_record(days_old=170))
        alerts = engine.generate_alerts()
        assert alerts[0].overdue_days == 0.0

    def test_alert_risk_score_capped_at_one(self):
        engine = _engine_with(_make_record(days_old=10000))
        alerts = engine.generate_alerts()
        assert alerts[0].risk_score == 1.0

    def test_freshness_level_set_on_records(self):
        rec = _make_record(days_old=300)
        engine = _engine_with(rec)
        engine.generate_alerts()
        assert rec.freshness_level == FreshnessLevel.EXPIRED

    def test_alert_age_days_is_positive(self):
        engine = _engine_with(_make_record(days_old=200))
        alerts = engine.generate_alerts()
        assert alerts[0].age_days > 0

    def test_alert_contains_component_id_in_recommendation(self):
        engine = _engine_with(_make_record(component_id="db-primary", days_old=200))
        alerts = engine.generate_alerts()
        assert "db-primary" in alerts[0].recommendation

    def test_alert_contains_item_name_in_recommendation(self):
        engine = _engine_with(_make_record(item_name="openssl", days_old=200))
        alerts = engine.generate_alerts()
        assert "openssl" in alerts[0].recommendation


# =========================================================================
# 8. calculate_freshness_score tests
# =========================================================================


class TestCalculateFreshnessScore:
    def test_no_records_returns_100(self):
        engine = FreshnessAlertEngine()
        assert engine.calculate_freshness_score() == 100.0

    def test_all_current(self):
        engine = _engine_with(
            _make_record(days_old=1),
            _make_record(days_old=5),
        )
        assert engine.calculate_freshness_score() == 100.0

    def test_all_expired(self):
        engine = _engine_with(
            _make_record(days_old=500),
            _make_record(days_old=600),
        )
        assert engine.calculate_freshness_score() == 0.0

    def test_mixed_levels(self):
        engine = _engine_with(
            _make_record(days_old=1),    # CURRENT => 100
            _make_record(days_old=500),  # EXPIRED => 0
        )
        score = engine.calculate_freshness_score()
        assert score == 50.0

    def test_single_aging_record(self):
        engine = _engine_with(_make_record(days_old=140))  # AGING
        assert engine.calculate_freshness_score() == 75.0

    def test_single_stale_record(self):
        engine = _engine_with(_make_record(days_old=165))  # STALE
        assert engine.calculate_freshness_score() == 50.0

    def test_single_critical_record(self):
        engine = _engine_with(_make_record(days_old=200))  # CRITICAL
        assert engine.calculate_freshness_score() == 25.0

    def test_score_is_rounded(self):
        # Three records: CURRENT(100) + AGING(75) + STALE(50) = 225/3 = 75.0
        engine = _engine_with(
            _make_record(days_old=1),
            _make_record(days_old=140),
            _make_record(days_old=165),
        )
        assert engine.calculate_freshness_score() == 75.0

    def test_score_between_0_and_100(self):
        engine = _engine_with(
            _make_record(days_old=1),
            _make_record(days_old=140),
            _make_record(days_old=165),
            _make_record(days_old=200),
            _make_record(days_old=500),
        )
        score = engine.calculate_freshness_score()
        assert 0.0 <= score <= 100.0


# =========================================================================
# 9. generate_report tests
# =========================================================================


class TestGenerateReport:
    def test_empty_report(self):
        engine = FreshnessAlertEngine()
        report = engine.generate_report()
        assert report.total_items == 0
        assert report.current_count == 0
        assert report.aging_count == 0
        assert report.stale_count == 0
        assert report.critical_count == 0
        assert report.expired_count == 0
        assert report.alerts == []
        assert report.overall_freshness_score == 100.0
        assert len(report.recommendations) > 0

    def test_report_counts_correct(self):
        engine = _engine_with(
            _make_record(component_id="a", days_old=1),    # CURRENT
            _make_record(component_id="b", days_old=140),  # AGING
            _make_record(component_id="c", days_old=165),  # STALE
            _make_record(component_id="d", days_old=200),  # CRITICAL
            _make_record(component_id="e", days_old=500),  # EXPIRED
        )
        report = engine.generate_report()
        assert report.total_items == 5
        assert report.current_count == 1
        assert report.aging_count == 1
        assert report.stale_count == 1
        assert report.critical_count == 1
        assert report.expired_count == 1

    def test_report_alerts_only_stale_critical_expired(self):
        engine = _engine_with(
            _make_record(component_id="a", days_old=1),    # CURRENT
            _make_record(component_id="b", days_old=140),  # AGING
            _make_record(component_id="c", days_old=165),  # STALE
        )
        report = engine.generate_report()
        assert len(report.alerts) == 1  # only STALE

    def test_report_overall_freshness_score(self):
        engine = _engine_with(
            _make_record(days_old=1),    # 100
            _make_record(days_old=500),  # 0
        )
        report = engine.generate_report()
        assert report.overall_freshness_score == 50.0

    def test_report_has_recommendations(self):
        engine = _engine_with(_make_record(days_old=500))
        report = engine.generate_report()
        assert len(report.recommendations) > 0

    def test_report_recommendation_urgent_for_expired(self):
        engine = _engine_with(_make_record(days_old=500))
        report = engine.generate_report()
        assert any("URGENT" in r for r in report.recommendations)

    def test_report_recommendation_critical_for_critical(self):
        engine = _engine_with(_make_record(days_old=200))
        report = engine.generate_report()
        assert any("CRITICAL" in r for r in report.recommendations)

    def test_report_recommendation_warning_for_stale(self):
        engine = _engine_with(_make_record(days_old=165))
        report = engine.generate_report()
        assert any("WARNING" in r for r in report.recommendations)

    def test_report_all_good_recommendation(self):
        engine = _engine_with(_make_record(days_old=1))
        report = engine.generate_report()
        assert any("acceptable" in r.lower() for r in report.recommendations)

    def test_report_is_freshnessreport_type(self):
        engine = FreshnessAlertEngine()
        report = engine.generate_report()
        assert isinstance(report, FreshnessReport)

    def test_report_freshness_level_set_on_records(self):
        rec = _make_record(days_old=1)
        engine = _engine_with(rec)
        engine.generate_report()
        assert rec.freshness_level == FreshnessLevel.CURRENT


# =========================================================================
# 10. _compute_age_days tests
# =========================================================================


class TestComputeAgeDays:
    def test_age_days_zero(self):
        rec = _make_record(days_old=0)
        age = FreshnessAlertEngine._compute_age_days(rec)
        assert age >= 0.0
        assert age < 0.1  # should be essentially zero

    def test_age_days_one(self):
        rec = _make_record(days_old=1)
        age = FreshnessAlertEngine._compute_age_days(rec)
        assert 0.9 < age < 1.1

    def test_age_days_large(self):
        rec = _make_record(days_old=365)
        age = FreshnessAlertEngine._compute_age_days(rec)
        assert 364.5 < age < 365.5

    def test_naive_datetime_treated_as_utc(self):
        rec = FreshnessRecord(
            component_id="x",
            category=FreshnessCategory.BACKUP,
            item_name="test",
            current_version="v1",
            last_updated=datetime(2020, 1, 1),  # naive, far in the past
            max_age_days=7,
        )
        age = FreshnessAlertEngine._compute_age_days(rec)
        assert age > 365  # definitely > 1 year old

    def test_never_negative(self):
        # Future date
        rec = FreshnessRecord(
            component_id="x",
            category=FreshnessCategory.BACKUP,
            item_name="test",
            current_version="v1",
            last_updated=_now() + timedelta(days=10),
            max_age_days=7,
        )
        age = FreshnessAlertEngine._compute_age_days(rec)
        assert age == 0.0


# =========================================================================
# 11. _build_alert tests
# =========================================================================


class TestBuildAlert:
    def test_stale_alert_recommendation(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=165)
        alert = engine._build_alert(rec, FreshnessLevel.STALE)
        assert "WARNING" in alert.recommendation
        assert rec.item_name in alert.recommendation

    def test_critical_alert_recommendation(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=200)
        alert = engine._build_alert(rec, FreshnessLevel.CRITICAL)
        assert "CRITICAL" in alert.recommendation

    def test_expired_alert_recommendation(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=300)
        alert = engine._build_alert(rec, FreshnessLevel.EXPIRED)
        assert "URGENT" in alert.recommendation

    def test_alert_risk_score_proportional_to_age(self):
        engine = FreshnessAlertEngine()
        rec_young = _make_record(days_old=165)
        rec_old = _make_record(days_old=250)
        alert_young = engine._build_alert(rec_young, FreshnessLevel.STALE)
        alert_old = engine._build_alert(rec_old, FreshnessLevel.CRITICAL)
        assert alert_old.risk_score > alert_young.risk_score

    def test_alert_overdue_positive_when_past_max(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=200)  # max_age=180
        alert = engine._build_alert(rec, FreshnessLevel.CRITICAL)
        assert alert.overdue_days > 0

    def test_alert_overdue_zero_when_within_max(self):
        engine = FreshnessAlertEngine()
        rec = _make_record(days_old=165)  # max_age=180
        alert = engine._build_alert(rec, FreshnessLevel.STALE)
        assert alert.overdue_days == 0.0


# =========================================================================
# 12. _make_recommendation tests
# =========================================================================


class TestMakeRecommendation:
    def test_expired_message(self):
        rec = _make_record(item_name="openssl")
        msg = FreshnessAlertEngine._make_recommendation(
            rec, FreshnessLevel.EXPIRED, 300, 180
        )
        assert "URGENT" in msg
        assert "openssl" in msg
        assert "immediately" in msg

    def test_critical_message(self):
        rec = _make_record(item_name="cert")
        msg = FreshnessAlertEngine._make_recommendation(
            rec, FreshnessLevel.CRITICAL, 200, 180
        )
        assert "CRITICAL" in msg
        assert "cert" in msg
        assert "week" in msg

    def test_stale_message(self):
        rec = _make_record(item_name="config")
        msg = FreshnessAlertEngine._make_recommendation(
            rec, FreshnessLevel.STALE, 170, 180
        )
        assert "WARNING" in msg
        assert "config" in msg
        assert "maintenance" in msg

    def test_contains_age(self):
        rec = _make_record()
        msg = FreshnessAlertEngine._make_recommendation(
            rec, FreshnessLevel.EXPIRED, 300, 180
        )
        assert "300" in msg

    def test_contains_max_age(self):
        rec = _make_record()
        msg = FreshnessAlertEngine._make_recommendation(
            rec, FreshnessLevel.EXPIRED, 300, 180
        )
        assert "180" in msg


# =========================================================================
# 13. _generate_recommendations tests
# =========================================================================


class TestGenerateRecommendations:
    def test_no_issues(self):
        counts = {lv: 0 for lv in FreshnessLevel}
        counts[FreshnessLevel.CURRENT] = 5
        recs = FreshnessAlertEngine._generate_recommendations(counts, [])
        assert len(recs) == 1
        assert "acceptable" in recs[0].lower()

    def test_expired_recommendation(self):
        counts = {lv: 0 for lv in FreshnessLevel}
        counts[FreshnessLevel.EXPIRED] = 2
        recs = FreshnessAlertEngine._generate_recommendations(counts, [])
        assert any("URGENT" in r for r in recs)
        assert any("2" in r for r in recs)

    def test_critical_recommendation(self):
        counts = {lv: 0 for lv in FreshnessLevel}
        counts[FreshnessLevel.CRITICAL] = 3
        recs = FreshnessAlertEngine._generate_recommendations(counts, [])
        assert any("CRITICAL" in r for r in recs)

    def test_stale_recommendation(self):
        counts = {lv: 0 for lv in FreshnessLevel}
        counts[FreshnessLevel.STALE] = 1
        recs = FreshnessAlertEngine._generate_recommendations(counts, [])
        assert any("WARNING" in r for r in recs)

    def test_combined_issues(self):
        counts = {lv: 0 for lv in FreshnessLevel}
        counts[FreshnessLevel.EXPIRED] = 1
        counts[FreshnessLevel.CRITICAL] = 2
        counts[FreshnessLevel.STALE] = 3
        recs = FreshnessAlertEngine._generate_recommendations(counts, [])
        assert len(recs) == 3  # one per severity


# =========================================================================
# 14. _LEVEL_SCORES constant tests
# =========================================================================


class TestLevelScores:
    def test_all_levels_have_scores(self):
        for level in FreshnessLevel:
            assert level in _LEVEL_SCORES

    def test_current_is_max(self):
        assert _LEVEL_SCORES[FreshnessLevel.CURRENT] == 100.0

    def test_expired_is_zero(self):
        assert _LEVEL_SCORES[FreshnessLevel.EXPIRED] == 0.0

    def test_scores_descend(self):
        ordered = [
            FreshnessLevel.CURRENT,
            FreshnessLevel.AGING,
            FreshnessLevel.STALE,
            FreshnessLevel.CRITICAL,
            FreshnessLevel.EXPIRED,
        ]
        for i in range(len(ordered) - 1):
            assert _LEVEL_SCORES[ordered[i]] > _LEVEL_SCORES[ordered[i + 1]]


# =========================================================================
# 15. _DEFAULT_MAX_AGE constant tests
# =========================================================================


class TestDefaultMaxAge:
    def test_all_categories_have_defaults(self):
        for cat in FreshnessCategory:
            assert cat in _DEFAULT_MAX_AGE

    def test_specific_values(self):
        assert _DEFAULT_MAX_AGE[FreshnessCategory.SOFTWARE_VERSION] == 180
        assert _DEFAULT_MAX_AGE[FreshnessCategory.CERTIFICATE] == 365
        assert _DEFAULT_MAX_AGE[FreshnessCategory.CONFIGURATION] == 90
        assert _DEFAULT_MAX_AGE[FreshnessCategory.PATCH_LEVEL] == 30
        assert _DEFAULT_MAX_AGE[FreshnessCategory.DEPENDENCY_VERSION] == 120
        assert _DEFAULT_MAX_AGE[FreshnessCategory.BACKUP] == 7
        assert _DEFAULT_MAX_AGE[FreshnessCategory.DOCUMENTATION] == 180
        assert _DEFAULT_MAX_AGE[FreshnessCategory.RUNBOOK] == 90

    def test_all_positive(self):
        for v in _DEFAULT_MAX_AGE.values():
            assert v > 0


# =========================================================================
# 16. Integration / scenario tests
# =========================================================================


class TestIntegrationScenarios:
    def test_full_workflow(self):
        """End-to-end: add records, set policy, generate report."""
        engine = FreshnessAlertEngine()
        engine.set_policy(FreshnessPolicy(
            category=FreshnessCategory.BACKUP, max_age_days=3
        ))
        engine.add_record(_make_record(
            component_id="web", category=FreshnessCategory.SOFTWARE_VERSION,
            item_name="nginx", days_old=10,
        ))
        engine.add_record(_make_record(
            component_id="db", category=FreshnessCategory.BACKUP,
            item_name="daily-backup", days_old=5,  # 5 days > 3*1.5=4.5 => EXPIRED
        ))
        report = engine.generate_report()
        assert report.total_items == 2
        assert report.expired_count == 1
        assert report.current_count == 1
        assert len(report.alerts) == 1
        assert report.alerts[0].record.component_id == "db"

    def test_multiple_categories(self):
        engine = FreshnessAlertEngine()
        for cat in FreshnessCategory:
            engine.add_record(_make_record(
                component_id=f"comp-{cat.value}",
                category=cat,
                days_old=1,
            ))
        report = engine.generate_report()
        assert report.total_items == 8
        assert report.current_count == 8
        assert report.overall_freshness_score == 100.0

    def test_all_expired_scenario(self):
        engine = FreshnessAlertEngine()
        for cat in FreshnessCategory:
            max_age = _DEFAULT_MAX_AGE[cat]
            engine.add_record(_make_record(
                component_id=f"comp-{cat.value}",
                category=cat,
                days_old=max_age * 2,
            ))
        report = engine.generate_report()
        assert report.expired_count == 8
        assert report.overall_freshness_score == 0.0
        assert len(report.alerts) == 8

    def test_custom_policy_affects_score(self):
        engine = FreshnessAlertEngine()
        # Default backup max = 7 days, custom = 365 days
        engine.set_policy(FreshnessPolicy(
            category=FreshnessCategory.BACKUP, max_age_days=365
        ))
        engine.add_record(_make_record(
            category=FreshnessCategory.BACKUP, days_old=10
        ))
        report = engine.generate_report()
        # 10 days old with 365-day max => CURRENT
        assert report.current_count == 1
        assert report.overall_freshness_score == 100.0

    def test_report_score_matches_calculate(self):
        engine = _engine_with(
            _make_record(days_old=1),
            _make_record(days_old=140),
            _make_record(days_old=165),
        )
        report = engine.generate_report()
        score = engine.calculate_freshness_score()
        assert report.overall_freshness_score == score

    def test_many_records_performance(self):
        """Sanity check: engine handles 1000 records."""
        engine = FreshnessAlertEngine()
        for i in range(1000):
            engine.add_record(_make_record(
                component_id=f"c-{i}", days_old=i % 300
            ))
        report = engine.generate_report()
        assert report.total_items == 1000
        assert 0.0 <= report.overall_freshness_score <= 100.0
