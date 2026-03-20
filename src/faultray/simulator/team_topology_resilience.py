# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Team Topology Resilience Analyzer.

Analyzes how team structure affects infrastructure resilience using
Conway's Law principles.  Maps team ownership to infrastructure
components, detects ownership gaps, cognitive overload, bus-factor
risks, and incident-response coverage gaps.

Based on the Team Topologies model (Skelton & Pais):
  - Stream-aligned teams
  - Platform teams
  - Enabling teams
  - Complicated-subsystem teams
"""

from __future__ import annotations

import logging
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TeamType(str, Enum):
    """Team Topologies fundamental team types."""

    STREAM_ALIGNED = "stream_aligned"
    PLATFORM = "platform"
    ENABLING = "enabling"
    COMPLICATED_SUBSYSTEM = "complicated_subsystem"


class InteractionMode(str, Enum):
    """Team Topologies interaction modes."""

    COLLABORATION = "collaboration"
    X_AS_A_SERVICE = "x_as_a_service"
    FACILITATING = "facilitating"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class Team(BaseModel):
    """A team that owns infrastructure components."""

    id: str
    name: str
    team_type: TeamType
    owned_components: list[str] = Field(default_factory=list)
    size: int = Field(default=1, ge=1)
    oncall_coverage_hours: float = Field(default=0.0, ge=0.0, le=168.0)
    cognitive_load_score: float = Field(default=5.0, ge=0.0, le=10.0)


class TeamInteraction(BaseModel):
    """An interaction between two teams."""

    team_a_id: str
    team_b_id: str
    mode: InteractionMode
    shared_components: list[str] = Field(default_factory=list)
    communication_frequency: str = "weekly"


class TeamResilienceReport(BaseModel):
    """Overall team-topology resilience report."""

    ownership_coverage: float = Field(default=0.0, ge=0.0, le=100.0)
    bus_factor_risks: list[str] = Field(default_factory=list)
    cognitive_overload_teams: list[str] = Field(default_factory=list)
    cross_team_dependencies: int = 0
    incident_response_gaps: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class IncidentResponseCoverage(BaseModel):
    """Incident response coverage analysis."""

    total_teams: int = 0
    teams_with_oncall: int = 0
    coverage_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    gaps: list[str] = Field(default_factory=list)
    average_coverage_hours: float = 0.0
    fully_covered_teams: int = 0


class TeamRecommendation(BaseModel):
    """A recommendation for improving team structure."""

    category: str = ""
    description: str = ""
    priority: str = "medium"
    affected_teams: list[str] = Field(default_factory=list)


class TeamLossImpact(BaseModel):
    """Impact of losing a team member."""

    team_id: str = ""
    team_name: str = ""
    original_size: int = 0
    remaining_size: int = 0
    affected_components: list[str] = Field(default_factory=list)
    cognitive_load_increase: float = 0.0
    new_cognitive_load: float = 0.0
    risk_level: str = "low"
    can_maintain_oncall: bool = True
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class TeamTopologyResilienceEngine:
    """Analyses how team topology affects infrastructure resilience."""

    # -- Ownership gaps -----------------------------------------------------

    def detect_ownership_gaps(
        self,
        graph: InfraGraph,
        teams: list[Team],
    ) -> list[str]:
        """Return component IDs that are not owned by any team."""
        all_component_ids = set(graph.components.keys())
        owned: set[str] = set()
        for team in teams:
            owned.update(team.owned_components)
        unowned = sorted(all_component_ids - owned)
        return unowned

    # -- Bus factor ---------------------------------------------------------

    def calculate_bus_factor(self, teams: list[Team]) -> dict[str, int]:
        """Return a mapping of team-id -> bus-factor.

        Bus factor is the minimum number of people whose departure would
        endanger the team's ability to maintain its components.  For small
        teams the bus factor equals the team size.  For teams with many
        components the effective bus factor is further capped by the ratio
        of components to members.
        """
        result: dict[str, int] = {}
        for team in teams:
            # A team's bus factor starts at its size
            bf = team.size
            # If there are more components than members, each member is more
            # critical — lower the bus factor proportionally.
            n_components = len(team.owned_components)
            if n_components > 0 and team.size > 0:
                components_per_member = n_components / team.size
                if components_per_member > 2:
                    bf = max(1, bf - int(components_per_member - 2))
            result[team.id] = bf
        return result

    # -- Cognitive overload -------------------------------------------------

    def detect_cognitive_overload(self, teams: list[Team]) -> list[str]:
        """Return team IDs whose cognitive_load_score exceeds the threshold (7.0)."""
        overloaded: list[str] = []
        for team in teams:
            if team.cognitive_load_score > 7.0:
                overloaded.append(team.id)
        return overloaded

    # -- Incident response coverage -----------------------------------------

    def analyze_incident_response_coverage(
        self,
        teams: list[Team],
    ) -> IncidentResponseCoverage:
        """Analyze on-call / incident response coverage across teams."""
        if not teams:
            return IncidentResponseCoverage()

        total = len(teams)
        teams_with_oncall = sum(1 for t in teams if t.oncall_coverage_hours > 0)
        fully_covered = sum(1 for t in teams if t.oncall_coverage_hours >= 168.0)

        avg_hours = (
            sum(t.oncall_coverage_hours for t in teams) / total if total else 0.0
        )

        gaps: list[str] = []
        for team in teams:
            if team.oncall_coverage_hours <= 0:
                gaps.append(f"{team.name} ({team.id}): no on-call coverage")
            elif team.oncall_coverage_hours < 40:
                gaps.append(
                    f"{team.name} ({team.id}): only "
                    f"{team.oncall_coverage_hours:.0f}h/week coverage"
                )
            elif team.oncall_coverage_hours < 168:
                gaps.append(
                    f"{team.name} ({team.id}): partial coverage "
                    f"({team.oncall_coverage_hours:.0f}h/168h)"
                )

        coverage_ratio = teams_with_oncall / total if total else 0.0

        return IncidentResponseCoverage(
            total_teams=total,
            teams_with_oncall=teams_with_oncall,
            coverage_ratio=round(coverage_ratio, 2),
            gaps=gaps,
            average_coverage_hours=round(avg_hours, 1),
            fully_covered_teams=fully_covered,
        )

    # -- Recommend team structure -------------------------------------------

    def recommend_team_structure(
        self,
        graph: InfraGraph,
        teams: list[Team],
    ) -> list[TeamRecommendation]:
        """Generate recommendations for improving team topology."""
        recs: list[TeamRecommendation] = []

        # 1. Ownership gaps
        gaps = self.detect_ownership_gaps(graph, teams)
        if gaps:
            recs.append(
                TeamRecommendation(
                    category="ownership",
                    description=(
                        f"{len(gaps)} component(s) have no team ownership: "
                        f"{', '.join(gaps[:5])}"
                        + (" ..." if len(gaps) > 5 else "")
                    ),
                    priority="high",
                )
            )

        # 2. Cognitive overload
        overloaded = self.detect_cognitive_overload(teams)
        for tid in overloaded:
            team = next((t for t in teams if t.id == tid), None)
            if team:
                recs.append(
                    TeamRecommendation(
                        category="cognitive_load",
                        description=(
                            f"Team '{team.name}' has a cognitive load score of "
                            f"{team.cognitive_load_score:.1f}/10. "
                            "Consider splitting responsibilities or adding members."
                        ),
                        priority="high",
                        affected_teams=[tid],
                    )
                )

        # 3. Bus factor risks
        bus_factors = self.calculate_bus_factor(teams)
        for tid, bf in bus_factors.items():
            if bf <= 1:
                team = next((t for t in teams if t.id == tid), None)
                if team:
                    recs.append(
                        TeamRecommendation(
                            category="bus_factor",
                            description=(
                                f"Team '{team.name}' has a bus factor of {bf}. "
                                "Cross-train members or add staff."
                            ),
                            priority="critical",
                            affected_teams=[tid],
                        )
                    )

        # 4. Incident response
        coverage = self.analyze_incident_response_coverage(teams)
        if coverage.coverage_ratio < 1.0:
            no_oncall = [t for t in teams if t.oncall_coverage_hours <= 0]
            if no_oncall:
                recs.append(
                    TeamRecommendation(
                        category="incident_response",
                        description=(
                            f"{len(no_oncall)} team(s) have no on-call coverage. "
                            "Establish on-call rotations."
                        ),
                        priority="critical",
                        affected_teams=[t.id for t in no_oncall],
                    )
                )

        # 5. Small teams owning many components
        for team in teams:
            if team.size <= 2 and len(team.owned_components) > 3:
                recs.append(
                    TeamRecommendation(
                        category="team_sizing",
                        description=(
                            f"Team '{team.name}' (size={team.size}) owns "
                            f"{len(team.owned_components)} components. "
                            "Consider expanding the team."
                        ),
                        priority="high",
                        affected_teams=[team.id],
                    )
                )

        # 6. Platform team recommendations
        has_platform = any(t.team_type == TeamType.PLATFORM for t in teams)
        if not has_platform and len(teams) >= 3:
            recs.append(
                TeamRecommendation(
                    category="team_topology",
                    description=(
                        "No platform team exists. Consider creating a platform "
                        "team to reduce cognitive load on stream-aligned teams."
                    ),
                    priority="medium",
                )
            )

        # 7. Enabling team recommendations
        has_enabling = any(t.team_type == TeamType.ENABLING for t in teams)
        overloaded_count = len(overloaded)
        if not has_enabling and overloaded_count >= 2:
            recs.append(
                TeamRecommendation(
                    category="team_topology",
                    description=(
                        f"{overloaded_count} teams are cognitively overloaded. "
                        "Consider adding an enabling team to help reduce load."
                    ),
                    priority="medium",
                )
            )

        return recs

    # -- Simulate team member loss ------------------------------------------

    def simulate_team_member_loss(
        self,
        teams: list[Team],
        team_id: str,
    ) -> TeamLossImpact:
        """Simulate losing one member from a team and assess the impact."""
        team = next((t for t in teams if t.id == team_id), None)
        if team is None:
            return TeamLossImpact(
                team_id=team_id,
                risk_level="unknown",
                recommendations=["Team not found"],
            )

        original = team.size
        remaining = max(0, original - 1)

        # Cognitive load increases when one person leaves
        if remaining > 0:
            load_factor = original / remaining
            new_load = min(10.0, team.cognitive_load_score * load_factor)
            load_increase = new_load - team.cognitive_load_score
        else:
            new_load = 10.0
            load_increase = 10.0 - team.cognitive_load_score

        # Determine risk level
        if remaining == 0:
            risk_level = "critical"
        elif remaining == 1:
            risk_level = "high"
        elif new_load > 8.0:
            risk_level = "high"
        elif new_load > 7.0:
            risk_level = "medium"
        else:
            risk_level = "low"

        # On-call sustainability
        # A team needs at least 2 members for a healthy on-call rotation
        can_maintain = remaining >= 2 or team.oncall_coverage_hours <= 0

        recs: list[str] = []
        if remaining == 0:
            recs.append("Team will be completely unstaffed. Immediate hiring required.")
        elif remaining == 1:
            recs.append(
                "Single-person team cannot sustain on-call or vacation coverage. "
                "Add at least one more member."
            )
        if new_load > 8.0:
            recs.append(
                "Cognitive load will exceed safe threshold. "
                "Offload components to other teams or hire."
            )
        if not can_maintain:
            recs.append("On-call rotation will not be sustainable with remaining staff.")

        return TeamLossImpact(
            team_id=team_id,
            team_name=team.name,
            original_size=original,
            remaining_size=remaining,
            affected_components=list(team.owned_components),
            cognitive_load_increase=round(load_increase, 2),
            new_cognitive_load=round(new_load, 2),
            risk_level=risk_level,
            can_maintain_oncall=can_maintain,
            recommendations=recs,
        )

    # -- Full assessment ----------------------------------------------------

    def assess_team_resilience(
        self,
        graph: InfraGraph,
        teams: list[Team],
        interactions: list[TeamInteraction],
    ) -> TeamResilienceReport:
        """Run a full team-topology resilience assessment."""
        # Ownership coverage
        all_ids = set(graph.components.keys())
        if all_ids:
            owned: set[str] = set()
            for t in teams:
                owned.update(c for c in t.owned_components if c in all_ids)
            coverage = (len(owned) / len(all_ids)) * 100.0
        else:
            coverage = 100.0 if teams else 0.0

        # Bus factor risks
        bus_factors = self.calculate_bus_factor(teams)
        bf_risks = [
            f"{tid} (bus_factor={bf})"
            for tid, bf in bus_factors.items()
            if bf <= 1
        ]

        # Cognitive overload
        overloaded = self.detect_cognitive_overload(teams)

        # Cross-team dependencies (number of interactions with shared components)
        cross_deps = 0
        for interaction in interactions:
            if interaction.shared_components:
                cross_deps += len(interaction.shared_components)
            else:
                cross_deps += 1

        # Incident response gaps
        ir_coverage = self.analyze_incident_response_coverage(teams)
        ir_gaps = ir_coverage.gaps

        # Recommendations
        recs_objs = self.recommend_team_structure(graph, teams)
        recs = [r.description for r in recs_objs]

        return TeamResilienceReport(
            ownership_coverage=round(_clamp(coverage), 1),
            bus_factor_risks=bf_risks,
            cognitive_overload_teams=overloaded,
            cross_team_dependencies=cross_deps,
            incident_response_gaps=ir_gaps,
            recommendations=recs,
        )
