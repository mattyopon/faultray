# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Tests for GAS Scanner and Personalization Analyzer."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from faultray.cli.main import app
from faultray.discovery.gas_scanner import (
    GASScanResult,
    GASRisk,
    GASScript,
    GASScanner,
)
from faultray.discovery.personalization_analyzer import (
    PersonalizationAnalyzer,
    PersonalizationReport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def scanner() -> GASScanner:
    return GASScanner()


@pytest.fixture()
def demo_result(scanner: GASScanner) -> GASScanResult:
    return scanner.scan_demo()


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _make_script(
    *,
    script_id: str = "s001",
    name: str = "テスト.gs",
    owner_status: str = "active",
    shared_with: list[str] | None = None,
    days_since_update: int = 10,
    triggers: list[dict] | None = None,
) -> GASScript:
    """Helper: create a minimal GASScript for testing."""
    now = datetime.now(tz=timezone.utc)
    return GASScript(
        id=script_id,
        name=name,
        owner_email="owner@example.co.jp",
        owner_name="テストユーザー",
        created_at=now - timedelta(days=100),
        updated_at=now - timedelta(days=days_since_update),
        last_executed=now - timedelta(days=1),
        shared_with=shared_with or ["owner@example.co.jp"],
        triggers=triggers or [],
        linked_services=[],
        drive_location="テスト部/テスト",
        status="active",
        owner_status=owner_status,
    )


# ---------------------------------------------------------------------------
# GASScanResult structure
# ---------------------------------------------------------------------------


class TestDemoScan:
    def test_returns_gas_scan_result(self, demo_result: GASScanResult) -> None:
        assert isinstance(demo_result, GASScanResult)

    def test_total_scripts_matches_list(self, demo_result: GASScanResult) -> None:
        assert demo_result.total_scripts == len(demo_result.scripts)

    def test_count_equals_sum_of_levels(self, demo_result: GASScanResult) -> None:
        assert (
            demo_result.critical_count + demo_result.warning_count + demo_result.ok_count
            == demo_result.total_scripts
        )

    def test_has_scripts(self, demo_result: GASScanResult) -> None:
        assert len(demo_result.scripts) > 0

    def test_has_risks(self, demo_result: GASScanResult) -> None:
        assert len(demo_result.risks) == demo_result.total_scripts

    def test_each_script_has_a_risk(self, demo_result: GASScanResult) -> None:
        script_ids = {s.id for s in demo_result.scripts}
        risk_ids = {r.script_id for r in demo_result.risks}
        assert script_ids == risk_ids

    def test_has_critical_scripts(self, demo_result: GASScanResult) -> None:
        assert demo_result.critical_count >= 1

    def test_has_warning_scripts(self, demo_result: GASScanResult) -> None:
        assert demo_result.warning_count >= 1

    def test_has_ok_scripts(self, demo_result: GASScanResult) -> None:
        assert demo_result.ok_count >= 1

    def test_organization_name_respected(self, scanner: GASScanner) -> None:
        result = scanner.scan_demo(org_name="サングローブ株式会社")
        assert result.organization == "サングローブ株式会社"

    def test_scan_timestamp_is_recent(self, demo_result: GASScanResult) -> None:
        now = datetime.now(tz=timezone.utc)
        delta = abs((now - demo_result.scan_timestamp).total_seconds())
        assert delta < 60  # within 1 minute

    def test_scripts_have_japanese_names(self, demo_result: GASScanResult) -> None:
        names = [s.name for s in demo_result.scripts]
        # At least one should contain Japanese characters
        has_japanese = any(
            any("\u3040" <= c <= "\u9fff" for c in name) for name in names
        )
        assert has_japanese

    def test_to_dict_serializable(self, demo_result: GASScanResult) -> None:
        d = demo_result.to_dict()
        serialized = json.dumps(d, ensure_ascii=False)
        assert isinstance(serialized, str)
        assert "scripts" in d
        assert "risks" in d


# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------


class TestRiskScoring:
    def test_departed_owner_gives_critical(self, scanner: GASScanner) -> None:
        script = _make_script(owner_status="departed", shared_with=["owner@example.co.jp"])
        risk = scanner._calculate_risk(script)
        assert risk.risk_level == "critical"

    def test_departed_owner_score_at_least_7(self, scanner: GASScanner) -> None:
        script = _make_script(owner_status="departed", shared_with=["owner@example.co.jp"])
        risk = scanner._calculate_risk(script)
        assert risk.risk_score >= 7

    def test_departed_owner_reason_present(self, scanner: GASScanner) -> None:
        script = _make_script(owner_status="departed")
        risk = scanner._calculate_risk(script)
        assert any("left" in r.lower() or "退職" in r or "departed" in r.lower() for r in risk.reasons)

    def test_single_owner_with_stale_gives_warning(self, scanner: GASScanner) -> None:
        # Single owner (score +3) + stale update (score +2) = 5 → warning
        script = _make_script(
            owner_status="active",
            shared_with=["owner@example.co.jp"],
            days_since_update=400,
        )
        risk = scanner._calculate_risk(script)
        assert risk.risk_level == "warning"

    def test_single_owner_reason_present(self, scanner: GASScanner) -> None:
        script = _make_script(shared_with=["owner@example.co.jp"])
        risk = scanner._calculate_risk(script)
        assert any("1" in r or "only" in r.lower() or "person" in r.lower() for r in risk.reasons)

    def test_stale_script_adds_risk(self, scanner: GASScanner) -> None:
        fresh = _make_script(shared_with=["a@b.com", "c@d.com"], days_since_update=10)
        stale = _make_script(shared_with=["a@b.com", "c@d.com"], days_since_update=400)
        risk_fresh = scanner._calculate_risk(fresh)
        risk_stale = scanner._calculate_risk(stale)
        assert risk_stale.risk_score > risk_fresh.risk_score

    def test_stale_script_reason_mentions_days(self, scanner: GASScanner) -> None:
        script = _make_script(shared_with=["a@b.com", "c@d.com"], days_since_update=400)
        risk = scanner._calculate_risk(script)
        assert any("days" in r.lower() or "日" in r for r in risk.reasons)

    def test_time_trigger_adds_risk(self, scanner: GASScanner) -> None:
        no_trigger = _make_script(shared_with=["a@b.com", "c@d.com"], triggers=[])
        with_trigger = _make_script(
            shared_with=["a@b.com", "c@d.com"],
            triggers=[{"type": "time", "schedule": "daily"}],
        )
        r_no = scanner._calculate_risk(no_trigger)
        r_with = scanner._calculate_risk(with_trigger)
        assert r_with.risk_score > r_no.risk_score

    def test_multiple_owners_reduces_risk(self, scanner: GASScanner) -> None:
        single = _make_script(
            owner_status="active",
            shared_with=["owner@example.co.jp"],
            days_since_update=10,
        )
        multi = _make_script(
            owner_status="active",
            shared_with=["a@b.com", "c@d.com", "e@f.com"],
            days_since_update=10,
        )
        r_single = scanner._calculate_risk(single)
        r_multi = scanner._calculate_risk(multi)
        assert r_single.risk_score > r_multi.risk_score

    def test_ok_script_risk_level(self, scanner: GASScanner) -> None:
        script = _make_script(
            owner_status="active",
            shared_with=["a@b.com", "b@c.com", "c@d.com"],
            days_since_update=30,
            triggers=[],
        )
        risk = scanner._calculate_risk(script)
        assert risk.risk_level == "ok"

    def test_risk_score_bounded_0_to_10(self, scanner: GASScanner) -> None:
        script = _make_script(
            owner_status="departed",
            shared_with=["owner@example.co.jp"],
            days_since_update=500,
            triggers=[{"type": "time"}],
        )
        risk = scanner._calculate_risk(script)
        assert 0 <= risk.risk_score <= 10


# ---------------------------------------------------------------------------
# Dependency inference
# ---------------------------------------------------------------------------


class TestDependencyInference:
    def test_invoice_script_infers_sheets(self, scanner: GASScanner) -> None:
        script = _make_script(name="請求書自動送信.gs")
        services = scanner._infer_dependencies(script)
        assert "Gmail" in services

    def test_sheet_keyword_infers_sheets(self, scanner: GASScanner) -> None:
        script = _make_script(name="売上集計レポート.gs")
        services = scanner._infer_dependencies(script)
        assert "Sheets" in services

    def test_calendar_keyword(self, scanner: GASScanner) -> None:
        script = _make_script(name="会議室カレンダー同期.gs")
        services = scanner._infer_dependencies(script)
        assert "Calendar" in services

    def test_default_fallback_to_sheets(self, scanner: GASScanner) -> None:
        script = _make_script(name="unknown_script.gs")
        services = scanner._infer_dependencies(script)
        assert "Sheets" in services


# ---------------------------------------------------------------------------
# Personalization Analyzer
# ---------------------------------------------------------------------------


class TestPersonalizationAnalyzer:
    def test_returns_personalization_report(self, demo_result: GASScanResult) -> None:
        analyzer = PersonalizationAnalyzer()
        report = analyzer.analyze_gas(demo_result)
        assert isinstance(report, PersonalizationReport)

    def test_report_org_matches(self, demo_result: GASScanResult) -> None:
        analyzer = PersonalizationAnalyzer()
        report = analyzer.analyze_gas(demo_result)
        assert report.organization == demo_result.organization

    def test_report_total_systems(self, demo_result: GASScanResult) -> None:
        analyzer = PersonalizationAnalyzer()
        report = analyzer.analyze_gas(demo_result)
        assert report.total_systems == demo_result.total_scripts

    def test_report_has_improvement_actions(self, demo_result: GASScanResult) -> None:
        analyzer = PersonalizationAnalyzer()
        report = analyzer.analyze_gas(demo_result)
        assert len(report.improvement_actions) > 0

    def test_critical_deps_contains_departed_owners(self, demo_result: GASScanResult) -> None:
        analyzer = PersonalizationAnalyzer()
        report = analyzer.analyze_gas(demo_result)
        departed_emails = {s.owner_email for s in demo_result.scripts if s.owner_status == "departed"}
        critical_emails = {d.person_email for d in report.critical_dependencies}
        assert departed_emails.issubset(critical_emails)

    def test_to_dict_is_serializable(self, demo_result: GASScanResult) -> None:
        analyzer = PersonalizationAnalyzer()
        report = analyzer.analyze_gas(demo_result)
        d = report.to_dict()
        json.dumps(d, ensure_ascii=False)  # should not raise


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


class TestGasScanCLI:
    def test_help_works(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["gas-scan", "--help"])
        assert result.exit_code == 0
        assert "gas-scan" in result.output.lower() or "GAS" in result.output

    def test_demo_mode_runs(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["gas-scan"])
        assert result.exit_code == 0

    def test_demo_mode_shows_results(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["gas-scan"])
        assert "Critical" in result.output or "CRITICAL" in result.output or "critical" in result.output

    def test_json_output_is_valid_json(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["gas-scan", "--json"])
        assert result.exit_code == 0
        # Extract JSON from output (may include ANSI codes; use json.loads on clean lines)
        output = result.output
        # Find the JSON block (starts with '{')
        json_start = output.find("{")
        assert json_start >= 0, "No JSON found in output"
        parsed = json.loads(output[json_start:])
        assert "scan" in parsed
        assert "personalization_report" in parsed

    def test_json_output_has_scripts(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["gas-scan", "--json"])
        output = result.output
        json_start = output.find("{")
        parsed = json.loads(output[json_start:])
        assert len(parsed["scan"]["scripts"]) > 0

    def test_org_name_appears_in_output(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["gas-scan", "--org", "テスト株式会社"])
        assert result.exit_code == 0
        assert "テスト株式会社" in result.output

    def test_missing_credentials_shows_demo_warning(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["gas-scan"])
        assert result.exit_code == 0
        assert "デモ" in result.output or "demo" in result.output.lower()
