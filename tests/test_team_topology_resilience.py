"""Tests for Team Topology Resilience Analyzer module."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph
from faultray.simulator.team_topology_resilience import (
    IncidentResponseCoverage,
    InteractionMode,
    Team,
    TeamInteraction,
    TeamLossImpact,
    TeamRecommendation,
    TeamResilienceReport,
    TeamTopologyResilienceEngine,
    TeamType,
    _clamp,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid: str, name: str | None = None) -> Component:
    return Component(id=cid, name=name or cid, type=ComponentType.APP_SERVER)


def _graph(*cids: str) -> InfraGraph:
    g = InfraGraph()
    for cid in cids:
        g.add_component(_comp(cid))
    return g


def _team(
    tid: str = "t1",
    name: str = "Alpha",
    *,
    team_type: TeamType = TeamType.STREAM_ALIGNED,
    owned: list[str] | None = None,
    size: int = 5,
    oncall: float = 168.0,
    cognitive: float = 5.0,
) -> Team:
    return Team(
        id=tid,
        name=name,
        team_type=team_type,
        owned_components=owned or [],
        size=size,
        oncall_coverage_hours=oncall,
        cognitive_load_score=cognitive,
    )


def _interaction(
    a: str = "t1",
    b: str = "t2",
    mode: InteractionMode = InteractionMode.COLLABORATION,
    shared: list[str] | None = None,
    freq: str = "weekly",
) -> TeamInteraction:
    return TeamInteraction(
        team_a_id=a,
        team_b_id=b,
        mode=mode,
        shared_components=shared or [],
        communication_frequency=freq,
    )


def _engine() -> TeamTopologyResilienceEngine:
    return TeamTopologyResilienceEngine()


# ===========================================================================
# Enum tests
# ===========================================================================


class TestTeamTypeEnum:
    def test_stream_aligned(self):
        assert TeamType.STREAM_ALIGNED == "stream_aligned"

    def test_platform(self):
        assert TeamType.PLATFORM == "platform"

    def test_enabling(self):
        assert TeamType.ENABLING == "enabling"

    def test_complicated_subsystem(self):
        assert TeamType.COMPLICATED_SUBSYSTEM == "complicated_subsystem"

    def test_all_values(self):
        assert len(TeamType) == 4

    def test_str_enum(self):
        assert isinstance(TeamType.STREAM_ALIGNED, str)


class TestInteractionModeEnum:
    def test_collaboration(self):
        assert InteractionMode.COLLABORATION == "collaboration"

    def test_x_as_a_service(self):
        assert InteractionMode.X_AS_A_SERVICE == "x_as_a_service"

    def test_facilitating(self):
        assert InteractionMode.FACILITATING == "facilitating"

    def test_all_values(self):
        assert len(InteractionMode) == 3


# ===========================================================================
# Pydantic model tests
# ===========================================================================


class TestTeamModel:
    def test_basic_creation(self):
        t = _team()
        assert t.id == "t1"
        assert t.name == "Alpha"
        assert t.team_type == TeamType.STREAM_ALIGNED

    def test_defaults(self):
        t = Team(id="x", name="X", team_type=TeamType.PLATFORM)
        assert t.owned_components == []
        assert t.size == 1
        assert t.oncall_coverage_hours == 0.0
        assert t.cognitive_load_score == 5.0

    def test_owned_components(self):
        t = _team(owned=["c1", "c2", "c3"])
        assert t.owned_components == ["c1", "c2", "c3"]

    def test_cognitive_load_rejects_high(self):
        with pytest.raises(Exception):
            _team(cognitive=15.0)

    def test_cognitive_load_rejects_low(self):
        with pytest.raises(Exception):
            _team(cognitive=-5.0)

    def test_oncall_rejects_high(self):
        with pytest.raises(Exception):
            _team(oncall=200.0)

    def test_oncall_rejects_low(self):
        with pytest.raises(Exception):
            _team(oncall=-10.0)

    def test_size_minimum(self):
        with pytest.raises(Exception):
            _team(size=0)

    def test_all_team_types(self):
        for tt in TeamType:
            t = _team(team_type=tt)
            assert t.team_type == tt

    def test_serialization(self):
        t = _team(owned=["c1"])
        d = t.model_dump()
        assert d["id"] == "t1"
        assert d["owned_components"] == ["c1"]

    def test_deserialization(self):
        data = {
            "id": "t1",
            "name": "Alpha",
            "team_type": "stream_aligned",
            "owned_components": ["c1"],
            "size": 3,
            "oncall_coverage_hours": 100.0,
            "cognitive_load_score": 6.0,
        }
        t = Team(**data)
        assert t.team_type == TeamType.STREAM_ALIGNED
        assert t.size == 3


class TestTeamInteractionModel:
    def test_basic(self):
        ti = _interaction()
        assert ti.team_a_id == "t1"
        assert ti.team_b_id == "t2"
        assert ti.mode == InteractionMode.COLLABORATION

    def test_defaults(self):
        ti = TeamInteraction(
            team_a_id="a", team_b_id="b", mode=InteractionMode.FACILITATING
        )
        assert ti.shared_components == []
        assert ti.communication_frequency == "weekly"

    def test_shared_components(self):
        ti = _interaction(shared=["db", "cache"])
        assert ti.shared_components == ["db", "cache"]

    def test_all_modes(self):
        for mode in InteractionMode:
            ti = _interaction(mode=mode)
            assert ti.mode == mode

    def test_serialization(self):
        ti = _interaction(shared=["c1"])
        d = ti.model_dump()
        assert d["team_a_id"] == "t1"
        assert d["shared_components"] == ["c1"]


class TestTeamResilienceReportModel:
    def test_defaults(self):
        r = TeamResilienceReport()
        assert r.ownership_coverage == 0.0
        assert r.bus_factor_risks == []
        assert r.cognitive_overload_teams == []
        assert r.cross_team_dependencies == 0
        assert r.incident_response_gaps == []
        assert r.recommendations == []

    def test_custom_values(self):
        r = TeamResilienceReport(
            ownership_coverage=85.0,
            bus_factor_risks=["t1"],
            cognitive_overload_teams=["t2"],
            cross_team_dependencies=3,
            incident_response_gaps=["gap1"],
            recommendations=["rec1"],
        )
        assert r.ownership_coverage == 85.0
        assert len(r.bus_factor_risks) == 1

    def test_coverage_rejects_high(self):
        with pytest.raises(Exception):
            TeamResilienceReport(ownership_coverage=150.0)

    def test_coverage_rejects_low(self):
        with pytest.raises(Exception):
            TeamResilienceReport(ownership_coverage=-10.0)


class TestIncidentResponseCoverageModel:
    def test_defaults(self):
        c = IncidentResponseCoverage()
        assert c.total_teams == 0
        assert c.teams_with_oncall == 0
        assert c.coverage_ratio == 0.0
        assert c.gaps == []

    def test_custom(self):
        c = IncidentResponseCoverage(
            total_teams=5,
            teams_with_oncall=3,
            coverage_ratio=0.6,
            gaps=["gap1"],
            average_coverage_hours=80.0,
            fully_covered_teams=2,
        )
        assert c.total_teams == 5
        assert c.fully_covered_teams == 2


class TestTeamRecommendationModel:
    def test_defaults(self):
        r = TeamRecommendation()
        assert r.category == ""
        assert r.priority == "medium"
        assert r.affected_teams == []

    def test_custom(self):
        r = TeamRecommendation(
            category="ownership",
            description="Fix gaps",
            priority="high",
            affected_teams=["t1", "t2"],
        )
        assert r.category == "ownership"


class TestTeamLossImpactModel:
    def test_defaults(self):
        li = TeamLossImpact()
        assert li.team_id == ""
        assert li.risk_level == "low"
        assert li.can_maintain_oncall is True

    def test_custom(self):
        li = TeamLossImpact(
            team_id="t1",
            team_name="Alpha",
            original_size=5,
            remaining_size=4,
            affected_components=["c1"],
            risk_level="medium",
        )
        assert li.remaining_size == 4


# ===========================================================================
# _clamp helper
# ===========================================================================


class TestClamp:
    def test_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_below_minimum(self):
        assert _clamp(-10.0) == 0.0

    def test_above_maximum(self):
        assert _clamp(150.0) == 100.0

    def test_at_boundaries(self):
        assert _clamp(0.0) == 0.0
        assert _clamp(100.0) == 100.0

    def test_custom_range(self):
        assert _clamp(5.0, 0.0, 10.0) == 5.0
        assert _clamp(-1.0, 0.0, 10.0) == 0.0
        assert _clamp(15.0, 0.0, 10.0) == 10.0


# ===========================================================================
# detect_ownership_gaps
# ===========================================================================


class TestDetectOwnershipGaps:
    def test_no_gaps(self):
        g = _graph("c1", "c2")
        teams = [_team(owned=["c1", "c2"])]
        result = _engine().detect_ownership_gaps(g, teams)
        assert result == []

    def test_all_unowned(self):
        g = _graph("c1", "c2", "c3")
        teams = [_team(owned=[])]
        result = _engine().detect_ownership_gaps(g, teams)
        assert sorted(result) == ["c1", "c2", "c3"]

    def test_partial_gap(self):
        g = _graph("c1", "c2", "c3")
        teams = [_team(owned=["c1"])]
        result = _engine().detect_ownership_gaps(g, teams)
        assert sorted(result) == ["c2", "c3"]

    def test_multiple_teams_cover_all(self):
        g = _graph("c1", "c2", "c3")
        teams = [
            _team(tid="t1", owned=["c1"]),
            _team(tid="t2", owned=["c2", "c3"]),
        ]
        result = _engine().detect_ownership_gaps(g, teams)
        assert result == []

    def test_empty_graph(self):
        g = InfraGraph()
        teams = [_team(owned=["c1"])]
        result = _engine().detect_ownership_gaps(g, teams)
        assert result == []

    def test_empty_teams(self):
        g = _graph("c1")
        result = _engine().detect_ownership_gaps(g, [])
        assert result == ["c1"]

    def test_overlapping_ownership(self):
        g = _graph("c1", "c2")
        teams = [
            _team(tid="t1", owned=["c1", "c2"]),
            _team(tid="t2", owned=["c1"]),
        ]
        result = _engine().detect_ownership_gaps(g, teams)
        assert result == []

    def test_returns_sorted(self):
        g = _graph("z", "a", "m")
        result = _engine().detect_ownership_gaps(g, [])
        assert result == ["a", "m", "z"]


# ===========================================================================
# calculate_bus_factor
# ===========================================================================


class TestCalculateBusFactor:
    def test_single_member(self):
        teams = [_team(size=1, owned=["c1"])]
        bf = _engine().calculate_bus_factor(teams)
        assert bf["t1"] == 1

    def test_large_team(self):
        teams = [_team(size=10, owned=["c1", "c2"])]
        bf = _engine().calculate_bus_factor(teams)
        assert bf["t1"] == 10

    def test_many_components_reduces_factor(self):
        # 2 members, 6 components -> 3 per member -> bf lowered by 1
        teams = [_team(size=2, owned=["c1", "c2", "c3", "c4", "c5", "c6"])]
        bf = _engine().calculate_bus_factor(teams)
        assert bf["t1"] < 2

    def test_no_components(self):
        teams = [_team(size=5, owned=[])]
        bf = _engine().calculate_bus_factor(teams)
        assert bf["t1"] == 5

    def test_multiple_teams(self):
        teams = [
            _team(tid="t1", size=1, owned=["c1"]),
            _team(tid="t2", name="Beta", size=5, owned=["c2"]),
        ]
        bf = _engine().calculate_bus_factor(teams)
        assert bf["t1"] == 1
        assert bf["t2"] == 5

    def test_empty_teams(self):
        bf = _engine().calculate_bus_factor([])
        assert bf == {}

    def test_bus_factor_minimum_one(self):
        # Even with huge component overload, bf should be at least 1
        teams = [_team(size=1, owned=[f"c{i}" for i in range(20)])]
        bf = _engine().calculate_bus_factor(teams)
        assert bf["t1"] >= 1

    def test_balanced_ratio(self):
        # 5 members, 5 components -> ratio 1 -> no reduction
        teams = [_team(size=5, owned=["c1", "c2", "c3", "c4", "c5"])]
        bf = _engine().calculate_bus_factor(teams)
        assert bf["t1"] == 5

    def test_two_components_per_member(self):
        # 3 members, 6 components -> ratio 2 -> no reduction (threshold is >2)
        teams = [_team(size=3, owned=[f"c{i}" for i in range(6)])]
        bf = _engine().calculate_bus_factor(teams)
        assert bf["t1"] == 3

    def test_three_plus_components_per_member(self):
        # 2 members, 8 components -> ratio 4 -> reduced by 2
        teams = [_team(size=2, owned=[f"c{i}" for i in range(8)])]
        bf = _engine().calculate_bus_factor(teams)
        assert bf["t1"] == max(1, 2 - int(8 / 2 - 2))


# ===========================================================================
# detect_cognitive_overload
# ===========================================================================


class TestDetectCognitiveOverload:
    def test_no_overload(self):
        teams = [_team(cognitive=5.0)]
        result = _engine().detect_cognitive_overload(teams)
        assert result == []

    def test_at_threshold(self):
        teams = [_team(cognitive=7.0)]
        result = _engine().detect_cognitive_overload(teams)
        assert result == []  # threshold is >7.0, not >=

    def test_over_threshold(self):
        teams = [_team(cognitive=7.5)]
        result = _engine().detect_cognitive_overload(teams)
        assert result == ["t1"]

    def test_max_cognitive_load(self):
        teams = [_team(cognitive=10.0)]
        result = _engine().detect_cognitive_overload(teams)
        assert result == ["t1"]

    def test_multiple_overloaded(self):
        teams = [
            _team(tid="t1", cognitive=8.0),
            _team(tid="t2", name="Beta", cognitive=9.0),
            _team(tid="t3", name="Gamma", cognitive=3.0),
        ]
        result = _engine().detect_cognitive_overload(teams)
        assert sorted(result) == ["t1", "t2"]

    def test_empty_teams(self):
        result = _engine().detect_cognitive_overload([])
        assert result == []

    def test_zero_cognitive_load(self):
        teams = [_team(cognitive=0.0)]
        result = _engine().detect_cognitive_overload(teams)
        assert result == []


# ===========================================================================
# analyze_incident_response_coverage
# ===========================================================================


class TestAnalyzeIncidentResponseCoverage:
    def test_full_coverage(self):
        teams = [_team(oncall=168.0)]
        result = _engine().analyze_incident_response_coverage(teams)
        assert result.total_teams == 1
        assert result.teams_with_oncall == 1
        assert result.fully_covered_teams == 1
        assert result.coverage_ratio == 1.0
        assert result.gaps == []

    def test_no_coverage(self):
        teams = [_team(oncall=0.0)]
        result = _engine().analyze_incident_response_coverage(teams)
        assert result.teams_with_oncall == 0
        assert result.coverage_ratio == 0.0
        assert len(result.gaps) == 1

    def test_partial_coverage(self):
        teams = [_team(oncall=80.0)]
        result = _engine().analyze_incident_response_coverage(teams)
        assert result.teams_with_oncall == 1
        assert result.fully_covered_teams == 0
        assert len(result.gaps) == 1
        assert "partial" in result.gaps[0].lower() or "80" in result.gaps[0]

    def test_low_coverage(self):
        teams = [_team(oncall=20.0)]
        result = _engine().analyze_incident_response_coverage(teams)
        assert len(result.gaps) == 1
        assert "20" in result.gaps[0]

    def test_mixed_teams(self):
        teams = [
            _team(tid="t1", oncall=168.0),
            _team(tid="t2", name="Beta", oncall=0.0),
            _team(tid="t3", name="Gamma", oncall=80.0),
        ]
        result = _engine().analyze_incident_response_coverage(teams)
        assert result.total_teams == 3
        assert result.teams_with_oncall == 2
        assert result.fully_covered_teams == 1
        assert len(result.gaps) == 2

    def test_empty_teams(self):
        result = _engine().analyze_incident_response_coverage([])
        assert result.total_teams == 0
        assert result.coverage_ratio == 0.0

    def test_average_hours(self):
        teams = [
            _team(tid="t1", oncall=100.0),
            _team(tid="t2", name="Beta", oncall=50.0),
        ]
        result = _engine().analyze_incident_response_coverage(teams)
        assert result.average_coverage_hours == 75.0

    def test_all_fully_covered(self):
        teams = [
            _team(tid="t1", oncall=168.0),
            _team(tid="t2", name="Beta", oncall=168.0),
        ]
        result = _engine().analyze_incident_response_coverage(teams)
        assert result.fully_covered_teams == 2
        assert result.gaps == []

    def test_coverage_ratio_precision(self):
        teams = [
            _team(tid="t1", oncall=168.0),
            _team(tid="t2", name="Beta", oncall=0.0),
            _team(tid="t3", name="Gamma", oncall=0.0),
        ]
        result = _engine().analyze_incident_response_coverage(teams)
        assert result.coverage_ratio == pytest.approx(0.33, abs=0.01)

    def test_coverage_is_instance(self):
        result = _engine().analyze_incident_response_coverage([])
        assert isinstance(result, IncidentResponseCoverage)


# ===========================================================================
# recommend_team_structure
# ===========================================================================


class TestRecommendTeamStructure:
    def test_no_issues(self):
        g = _graph("c1")
        teams = [
            _team(
                owned=["c1"],
                size=5,
                oncall=168.0,
                cognitive=3.0,
                team_type=TeamType.PLATFORM,
            )
        ]
        recs = _engine().recommend_team_structure(g, teams)
        # No ownership gaps, no overload, reasonable bus factor, has oncall
        # Single team doesn't trigger platform-team suggestion
        assert isinstance(recs, list)

    def test_ownership_gap_recommendation(self):
        g = _graph("c1", "c2", "c3")
        teams = [_team(owned=["c1"])]
        recs = _engine().recommend_team_structure(g, teams)
        ownership_recs = [r for r in recs if r.category == "ownership"]
        assert len(ownership_recs) >= 1

    def test_cognitive_overload_recommendation(self):
        g = _graph("c1")
        teams = [_team(owned=["c1"], cognitive=9.0)]
        recs = _engine().recommend_team_structure(g, teams)
        cog_recs = [r for r in recs if r.category == "cognitive_load"]
        assert len(cog_recs) >= 1

    def test_bus_factor_recommendation(self):
        g = _graph("c1")
        teams = [_team(owned=["c1"], size=1)]
        recs = _engine().recommend_team_structure(g, teams)
        bf_recs = [r for r in recs if r.category == "bus_factor"]
        assert len(bf_recs) >= 1
        assert bf_recs[0].priority == "critical"

    def test_incident_response_recommendation(self):
        g = _graph("c1")
        teams = [_team(owned=["c1"], oncall=0.0)]
        recs = _engine().recommend_team_structure(g, teams)
        ir_recs = [r for r in recs if r.category == "incident_response"]
        assert len(ir_recs) >= 1

    def test_small_team_many_components(self):
        g = _graph("c1", "c2", "c3", "c4")
        teams = [_team(owned=["c1", "c2", "c3", "c4"], size=2)]
        recs = _engine().recommend_team_structure(g, teams)
        sizing_recs = [r for r in recs if r.category == "team_sizing"]
        assert len(sizing_recs) >= 1

    def test_no_platform_team_suggestion(self):
        g = _graph("c1", "c2", "c3")
        teams = [
            _team(tid="t1", owned=["c1"]),
            _team(tid="t2", name="Beta", owned=["c2"]),
            _team(tid="t3", name="Gamma", owned=["c3"]),
        ]
        recs = _engine().recommend_team_structure(g, teams)
        topo_recs = [
            r
            for r in recs
            if r.category == "team_topology" and "platform" in r.description.lower()
        ]
        assert len(topo_recs) >= 1

    def test_has_platform_team_no_suggestion(self):
        g = _graph("c1", "c2", "c3")
        teams = [
            _team(tid="t1", owned=["c1"], team_type=TeamType.PLATFORM),
            _team(tid="t2", name="Beta", owned=["c2"]),
            _team(tid="t3", name="Gamma", owned=["c3"]),
        ]
        recs = _engine().recommend_team_structure(g, teams)
        topo_recs = [
            r
            for r in recs
            if r.category == "team_topology" and "platform" in r.description.lower()
        ]
        assert len(topo_recs) == 0

    def test_enabling_team_recommendation(self):
        g = _graph("c1", "c2")
        teams = [
            _team(tid="t1", owned=["c1"], cognitive=8.5),
            _team(tid="t2", name="Beta", owned=["c2"], cognitive=8.0),
        ]
        recs = _engine().recommend_team_structure(g, teams)
        enable_recs = [
            r
            for r in recs
            if r.category == "team_topology" and "enabling" in r.description.lower()
        ]
        assert len(enable_recs) >= 1

    def test_recommendation_has_affected_teams(self):
        g = _graph("c1")
        teams = [_team(owned=["c1"], cognitive=9.0)]
        recs = _engine().recommend_team_structure(g, teams)
        cog_recs = [r for r in recs if r.category == "cognitive_load"]
        assert cog_recs[0].affected_teams == ["t1"]

    def test_empty_graph_no_teams(self):
        g = InfraGraph()
        recs = _engine().recommend_team_structure(g, [])
        assert isinstance(recs, list)

    def test_recommendation_is_TeamRecommendation(self):
        g = _graph("c1")
        teams = [_team(owned=[])]
        recs = _engine().recommend_team_structure(g, teams)
        for r in recs:
            assert isinstance(r, TeamRecommendation)

    def test_ownership_gap_truncated_at_five(self):
        cids = [f"c{i}" for i in range(10)]
        g = _graph(*cids)
        teams = [_team(owned=[])]
        recs = _engine().recommend_team_structure(g, teams)
        ownership_recs = [r for r in recs if r.category == "ownership"]
        assert len(ownership_recs) == 1
        assert "..." in ownership_recs[0].description


# ===========================================================================
# simulate_team_member_loss
# ===========================================================================


class TestSimulateTeamMemberLoss:
    def test_large_team_loss(self):
        teams = [_team(size=10, cognitive=3.0)]
        result = _engine().simulate_team_member_loss(teams, "t1")
        assert result.original_size == 10
        assert result.remaining_size == 9
        assert result.risk_level == "low"
        assert result.can_maintain_oncall is True

    def test_two_person_team_loss(self):
        teams = [_team(size=2, oncall=168.0, cognitive=5.0)]
        result = _engine().simulate_team_member_loss(teams, "t1")
        assert result.remaining_size == 1
        assert result.risk_level == "high"

    def test_single_person_team_loss(self):
        teams = [_team(size=1, cognitive=5.0)]
        result = _engine().simulate_team_member_loss(teams, "t1")
        assert result.remaining_size == 0
        assert result.risk_level == "critical"
        assert len(result.recommendations) > 0

    def test_team_not_found(self):
        teams = [_team(tid="t1")]
        result = _engine().simulate_team_member_loss(teams, "nonexistent")
        assert result.risk_level == "unknown"
        assert "not found" in result.recommendations[0].lower()

    def test_cognitive_load_increases(self):
        teams = [_team(size=5, cognitive=5.0)]
        result = _engine().simulate_team_member_loss(teams, "t1")
        assert result.new_cognitive_load > 5.0
        assert result.cognitive_load_increase > 0

    def test_cognitive_load_max_cap(self):
        teams = [_team(size=2, cognitive=9.0)]
        result = _engine().simulate_team_member_loss(teams, "t1")
        assert result.new_cognitive_load <= 10.0

    def test_affected_components(self):
        teams = [_team(owned=["c1", "c2", "c3"])]
        result = _engine().simulate_team_member_loss(teams, "t1")
        assert result.affected_components == ["c1", "c2", "c3"]

    def test_oncall_sustainability_large_team(self):
        teams = [_team(size=5, oncall=168.0)]
        result = _engine().simulate_team_member_loss(teams, "t1")
        assert result.can_maintain_oncall is True

    def test_oncall_sustainability_two_members(self):
        teams = [_team(size=2, oncall=168.0)]
        result = _engine().simulate_team_member_loss(teams, "t1")
        # 2 -> 1 member with on-call: not sustainable
        assert result.can_maintain_oncall is False

    def test_no_oncall_team(self):
        teams = [_team(size=2, oncall=0.0)]
        result = _engine().simulate_team_member_loss(teams, "t1")
        # No on-call to sustain
        assert result.can_maintain_oncall is True

    def test_high_cognitive_after_loss_recommendation(self):
        teams = [_team(size=2, cognitive=5.0)]
        result = _engine().simulate_team_member_loss(teams, "t1")
        # cognitive goes from 5.0 to 10.0 (5.0 * 2/1)
        assert result.new_cognitive_load == 10.0
        has_cog_rec = any("cognitive" in r.lower() for r in result.recommendations)
        assert has_cog_rec

    def test_high_cognitive_remaining_multiple_members(self):
        # size=3, cognitive=7.0 -> remaining=2, new_load=7.0*3/2=10.5->10.0
        # remaining > 1 but new_load > 8.0 -> risk_level == "high"
        teams = [_team(size=3, cognitive=7.0)]
        result = _engine().simulate_team_member_loss(teams, "t1")
        assert result.remaining_size == 2
        assert result.new_cognitive_load > 8.0
        assert result.risk_level == "high"

    def test_result_type(self):
        teams = [_team()]
        result = _engine().simulate_team_member_loss(teams, "t1")
        assert isinstance(result, TeamLossImpact)

    def test_team_name_preserved(self):
        teams = [_team(name="TheTeam")]
        result = _engine().simulate_team_member_loss(teams, "t1")
        assert result.team_name == "TheTeam"


# ===========================================================================
# assess_team_resilience (full assessment)
# ===========================================================================


class TestAssessTeamResilience:
    def test_perfect_setup(self):
        g = _graph("c1", "c2")
        teams = [
            _team(
                tid="t1",
                owned=["c1", "c2"],
                size=5,
                oncall=168.0,
                cognitive=3.0,
                team_type=TeamType.PLATFORM,
            )
        ]
        interactions: list[TeamInteraction] = []
        report = _engine().assess_team_resilience(g, teams, interactions)
        assert report.ownership_coverage == 100.0
        assert report.bus_factor_risks == []
        assert report.cognitive_overload_teams == []
        assert report.cross_team_dependencies == 0

    def test_no_ownership(self):
        g = _graph("c1", "c2")
        teams = [_team(owned=[])]
        report = _engine().assess_team_resilience(g, teams, [])
        assert report.ownership_coverage == 0.0

    def test_partial_ownership(self):
        g = _graph("c1", "c2", "c3", "c4")
        teams = [_team(owned=["c1", "c2"])]
        report = _engine().assess_team_resilience(g, teams, [])
        assert report.ownership_coverage == 50.0

    def test_bus_factor_risk_reported(self):
        g = _graph("c1")
        teams = [_team(owned=["c1"], size=1)]
        report = _engine().assess_team_resilience(g, teams, [])
        assert len(report.bus_factor_risks) >= 1
        assert "t1" in report.bus_factor_risks[0]

    def test_cognitive_overload_reported(self):
        g = _graph("c1")
        teams = [_team(owned=["c1"], cognitive=9.0)]
        report = _engine().assess_team_resilience(g, teams, [])
        assert "t1" in report.cognitive_overload_teams

    def test_cross_team_deps_from_interactions(self):
        g = _graph("c1", "c2")
        teams = [
            _team(tid="t1", owned=["c1"]),
            _team(tid="t2", name="Beta", owned=["c2"]),
        ]
        interactions = [_interaction(shared=["c1"])]
        report = _engine().assess_team_resilience(g, teams, interactions)
        assert report.cross_team_dependencies == 1

    def test_multiple_shared_components_counted(self):
        g = _graph("c1", "c2", "c3")
        teams = [
            _team(tid="t1", owned=["c1"]),
            _team(tid="t2", name="Beta", owned=["c2", "c3"]),
        ]
        interactions = [_interaction(shared=["c1", "c2"])]
        report = _engine().assess_team_resilience(g, teams, interactions)
        assert report.cross_team_dependencies == 2

    def test_no_shared_components_counts_one(self):
        g = _graph("c1")
        teams = [_team(owned=["c1"])]
        interactions = [_interaction()]
        report = _engine().assess_team_resilience(g, teams, interactions)
        assert report.cross_team_dependencies == 1

    def test_incident_response_gaps_reported(self):
        g = _graph("c1")
        teams = [_team(owned=["c1"], oncall=0.0)]
        report = _engine().assess_team_resilience(g, teams, [])
        assert len(report.incident_response_gaps) >= 1

    def test_recommendations_populated(self):
        g = _graph("c1", "c2")
        teams = [_team(owned=["c1"], size=1, oncall=0.0, cognitive=8.5)]
        report = _engine().assess_team_resilience(g, teams, [])
        assert len(report.recommendations) > 0

    def test_empty_graph_empty_teams(self):
        g = InfraGraph()
        report = _engine().assess_team_resilience(g, [], [])
        assert report.ownership_coverage == 0.0
        assert report.cross_team_dependencies == 0

    def test_empty_graph_with_teams(self):
        g = InfraGraph()
        teams = [_team(owned=["c1"])]
        report = _engine().assess_team_resilience(g, teams, [])
        assert report.ownership_coverage == 100.0

    def test_report_type(self):
        g = _graph("c1")
        teams = [_team(owned=["c1"])]
        report = _engine().assess_team_resilience(g, teams, [])
        assert isinstance(report, TeamResilienceReport)

    def test_ownership_only_counts_existing_components(self):
        g = _graph("c1", "c2")
        # Team claims c3 which doesn't exist in graph
        teams = [_team(owned=["c1", "c3"])]
        report = _engine().assess_team_resilience(g, teams, [])
        # Only c1 exists in graph and is owned; c2 is unowned
        assert report.ownership_coverage == 50.0

    def test_multiple_interactions(self):
        g = _graph("c1", "c2", "c3")
        teams = [
            _team(tid="t1", owned=["c1"]),
            _team(tid="t2", name="Beta", owned=["c2"]),
            _team(tid="t3", name="Gamma", owned=["c3"]),
        ]
        interactions = [
            _interaction(a="t1", b="t2", shared=["c1"]),
            _interaction(a="t2", b="t3", shared=["c2", "c3"]),
        ]
        report = _engine().assess_team_resilience(g, teams, interactions)
        assert report.cross_team_dependencies == 3

    def test_bus_factor_not_risk_when_large_team(self):
        g = _graph("c1")
        teams = [_team(owned=["c1"], size=10)]
        report = _engine().assess_team_resilience(g, teams, [])
        assert report.bus_factor_risks == []


# ===========================================================================
# Integration / edge-case tests
# ===========================================================================


class TestIntegration:
    def test_full_workflow(self):
        """End-to-end: graph -> teams -> interactions -> report."""
        g = _graph("api", "db", "cache", "queue", "worker")
        teams = [
            _team(
                tid="backend",
                name="Backend Team",
                owned=["api", "db"],
                size=4,
                oncall=168.0,
                cognitive=6.0,
            ),
            _team(
                tid="infra",
                name="Infra Team",
                team_type=TeamType.PLATFORM,
                owned=["cache", "queue"],
                size=3,
                oncall=168.0,
                cognitive=5.0,
            ),
        ]
        interactions = [
            _interaction(
                a="backend",
                b="infra",
                mode=InteractionMode.X_AS_A_SERVICE,
                shared=["cache"],
            )
        ]
        engine = _engine()
        report = engine.assess_team_resilience(g, teams, interactions)
        # worker is unowned
        assert report.ownership_coverage < 100.0
        assert report.cross_team_dependencies == 1
        assert isinstance(report, TeamResilienceReport)

        # Also check sub-methods
        gaps = engine.detect_ownership_gaps(g, teams)
        assert "worker" in gaps

        bf = engine.calculate_bus_factor(teams)
        assert "backend" in bf
        assert "infra" in bf

        overloaded = engine.detect_cognitive_overload(teams)
        assert overloaded == []

        coverage = engine.analyze_incident_response_coverage(teams)
        assert coverage.coverage_ratio == 1.0

        recs = engine.recommend_team_structure(g, teams)
        ownership_recs = [r for r in recs if r.category == "ownership"]
        assert len(ownership_recs) >= 1

        impact = engine.simulate_team_member_loss(teams, "infra")
        assert impact.remaining_size == 2
        assert impact.risk_level in ("low", "medium")

    def test_worst_case_scenario(self):
        """A dysfunctional team setup should produce many issues."""
        g = _graph("c1", "c2", "c3", "c4", "c5")
        teams = [
            _team(
                tid="lone",
                name="Lone Wolf",
                owned=["c1"],
                size=1,
                oncall=0.0,
                cognitive=9.5,
            )
        ]
        interactions: list[TeamInteraction] = []
        engine = _engine()
        report = engine.assess_team_resilience(g, teams, interactions)

        # Very low coverage
        assert report.ownership_coverage == 20.0
        # High bus factor risk
        assert len(report.bus_factor_risks) >= 1
        # Cognitive overload
        assert "lone" in report.cognitive_overload_teams
        # Incident response gaps
        assert len(report.incident_response_gaps) >= 1
        # Many recommendations
        assert len(report.recommendations) >= 3

    def test_ideal_scenario(self):
        """A well-structured team should produce few or no issues."""
        components = ["api", "db", "cache"]
        g = _graph(*components)
        teams = [
            _team(
                tid="stream",
                name="Stream Team",
                owned=["api", "db", "cache"],
                size=6,
                oncall=168.0,
                cognitive=4.0,
                team_type=TeamType.STREAM_ALIGNED,
            ),
            _team(
                tid="platform",
                name="Platform Team",
                team_type=TeamType.PLATFORM,
                owned=[],
                size=4,
                oncall=168.0,
                cognitive=3.0,
            ),
        ]
        engine = _engine()
        report = engine.assess_team_resilience(g, teams, [])
        assert report.ownership_coverage == 100.0
        assert report.bus_factor_risks == []
        assert report.cognitive_overload_teams == []

    def test_all_interaction_modes(self):
        """Test with all three interaction modes."""
        g = _graph("c1", "c2", "c3")
        teams = [
            _team(tid="t1", owned=["c1"]),
            _team(tid="t2", name="Beta", owned=["c2"]),
            _team(tid="t3", name="Gamma", owned=["c3"]),
        ]
        interactions = [
            _interaction(a="t1", b="t2", mode=InteractionMode.COLLABORATION, shared=["c1"]),
            _interaction(a="t2", b="t3", mode=InteractionMode.X_AS_A_SERVICE, shared=["c2"]),
            _interaction(a="t1", b="t3", mode=InteractionMode.FACILITATING, shared=[]),
        ]
        report = _engine().assess_team_resilience(g, teams, interactions)
        # 1 + 1 + 1 (empty shared counts as 1)
        assert report.cross_team_dependencies == 3

    def test_all_team_types_in_org(self):
        """Organization with all four team types."""
        g = _graph("c1", "c2", "c3", "c4")
        teams = [
            _team(tid="sa", name="Stream A", team_type=TeamType.STREAM_ALIGNED, owned=["c1"]),
            _team(tid="plat", name="Platform", team_type=TeamType.PLATFORM, owned=["c2"]),
            _team(tid="en", name="Enabling", team_type=TeamType.ENABLING, owned=["c3"]),
            _team(
                tid="cs",
                name="Complicated",
                team_type=TeamType.COMPLICATED_SUBSYSTEM,
                owned=["c4"],
            ),
        ]
        report = _engine().assess_team_resilience(g, teams, [])
        assert report.ownership_coverage == 100.0

    def test_large_organization(self):
        """Many teams and many components."""
        n_components = 50
        cids = [f"c{i}" for i in range(n_components)]
        g = _graph(*cids)
        teams = [
            _team(
                tid=f"team_{i}",
                name=f"Team {i}",
                owned=cids[i * 5 : (i + 1) * 5],
                size=5,
                oncall=168.0,
                cognitive=5.0,
            )
            for i in range(10)
        ]
        report = _engine().assess_team_resilience(g, teams, [])
        assert report.ownership_coverage == 100.0

    def test_simulate_loss_all_teams(self):
        """Simulate member loss across every team."""
        teams = [
            _team(tid="t1", size=1, oncall=168.0),
            _team(tid="t2", name="Beta", size=3, oncall=100.0),
            _team(tid="t3", name="Gamma", size=10, oncall=168.0),
        ]
        engine = _engine()
        results = {t.id: engine.simulate_team_member_loss(teams, t.id) for t in teams}
        assert results["t1"].risk_level == "critical"
        assert results["t2"].risk_level in ("low", "medium")
        assert results["t3"].risk_level == "low"

    def test_communication_frequency_values(self):
        """Various communication frequency strings."""
        for freq in ["daily", "weekly", "monthly", "as_needed"]:
            ti = _interaction(freq=freq)
            assert ti.communication_frequency == freq

    def test_team_with_only_nonexistent_components(self):
        """Team owns components not in the graph."""
        g = _graph("c1")
        teams = [_team(owned=["x1", "x2"])]
        gaps = _engine().detect_ownership_gaps(g, teams)
        assert "c1" in gaps

    def test_engine_reusable(self):
        """Same engine instance can be used for multiple analyses."""
        engine = _engine()
        g1 = _graph("c1")
        g2 = _graph("c2", "c3")
        teams1 = [_team(owned=["c1"])]
        teams2 = [_team(owned=["c2", "c3"])]

        r1 = engine.assess_team_resilience(g1, teams1, [])
        r2 = engine.assess_team_resilience(g2, teams2, [])
        assert r1.ownership_coverage == 100.0
        assert r2.ownership_coverage == 100.0

    def test_overlapping_team_ownership_in_assessment(self):
        """Two teams own the same component; coverage should still be 100%."""
        g = _graph("c1", "c2")
        teams = [
            _team(tid="t1", owned=["c1", "c2"]),
            _team(tid="t2", name="Beta", owned=["c1"]),
        ]
        report = _engine().assess_team_resilience(g, teams, [])
        assert report.ownership_coverage == 100.0

    def test_cognitive_overload_boundary_values(self):
        """Test cognitive load values at various boundaries."""
        engine = _engine()
        teams_low = [_team(cognitive=0.0)]
        teams_threshold = [_team(cognitive=7.0)]
        teams_just_over = [_team(cognitive=7.01)]
        teams_max = [_team(cognitive=10.0)]

        assert engine.detect_cognitive_overload(teams_low) == []
        assert engine.detect_cognitive_overload(teams_threshold) == []
        assert engine.detect_cognitive_overload(teams_just_over) == ["t1"]
        assert engine.detect_cognitive_overload(teams_max) == ["t1"]
