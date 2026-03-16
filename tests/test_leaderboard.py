"""Tests for the Resilience Leaderboard."""

from faultray.api.leaderboard import (
    BADGE_CRITERIA,
    LeaderboardEntry,
    LeaderboardStore,
    evaluate_badges,
    get_leaderboard_store,
)
from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


def _make_graph(replicas: int = 2) -> InfraGraph:
    """Build a simple graph for badge testing."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=replicas,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=replicas,
    ))
    return graph


def test_submit_and_retrieve():
    """Submitting a score should make it retrievable."""
    store = LeaderboardStore()
    entry = store.submit("Team A", score=85.0)
    assert entry.team_name == "Team A"
    assert entry.score == 85.0
    assert entry.rank == 1

    retrieved = store.get_team("Team A")
    assert retrieved is not None
    assert retrieved.score == 85.0


def test_ranking_order():
    """Teams should be ranked by score descending."""
    store = LeaderboardStore()
    store.submit("Low", score=50.0)
    store.submit("High", score=90.0)
    store.submit("Mid", score=70.0)

    board = store.get_leaderboard()
    assert len(board) == 3
    assert board[0].team_name == "High"
    assert board[0].rank == 1
    assert board[1].team_name == "Mid"
    assert board[1].rank == 2
    assert board[2].team_name == "Low"
    assert board[2].rank == 3


def test_score_delta_calculation():
    """Delta should reflect the change from previous submission."""
    store = LeaderboardStore()
    entry1 = store.submit("Team X", score=60.0)
    assert entry1.score_delta == 0.0  # first submission, no delta

    entry2 = store.submit("Team X", score=75.0)
    assert entry2.score_delta == 15.0

    entry3 = store.submit("Team X", score=70.0)
    assert entry3.score_delta == -5.0


def test_team_history():
    """Score history should track all submissions."""
    store = LeaderboardStore()
    store.submit("Team Y", score=50.0)
    store.submit("Team Y", score=60.0)
    store.submit("Team Y", score=55.0)

    history = store.get_team_history("Team Y")
    assert history == [50.0, 60.0, 55.0]


def test_badge_slo_champion():
    """Score >= 95 should earn the slo_champion badge."""
    badges = evaluate_badges(score=95.0)
    assert "slo_champion" in badges

    badges_low = evaluate_badges(score=94.0)
    assert "slo_champion" not in badges_low


def test_badge_spof_slayer():
    """All replicas >= 2 should earn spof_slayer."""
    graph_good = _make_graph(replicas=2)
    badges = evaluate_badges(score=80.0, graph=graph_good)
    assert "spof_slayer" in badges

    graph_bad = _make_graph(replicas=1)
    badges_bad = evaluate_badges(score=80.0, graph=graph_bad)
    assert "spof_slayer" not in badges_bad


def test_badge_rising_star():
    """Score improvement >= 10 should earn rising_star."""
    badges = evaluate_badges(score=70.0, delta=10.0)
    assert "rising_star" in badges

    badges_small = evaluate_badges(score=70.0, delta=5.0)
    assert "rising_star" not in badges_small


def test_badge_security_ace():
    """Security score >= 90 should earn security_ace."""
    badges = evaluate_badges(score=80.0, security_score=90.0)
    assert "security_ace" in badges

    badges_low = evaluate_badges(score=80.0, security_score=89.0)
    assert "security_ace" not in badges_low


def test_badge_first_steps():
    """Any score > 0 should earn first_steps."""
    badges = evaluate_badges(score=1.0)
    assert "first_steps" in badges

    badges_zero = evaluate_badges(score=0.0)
    assert "first_steps" not in badges_zero


def test_leaderboard_limit():
    """Leaderboard should respect the limit parameter."""
    store = LeaderboardStore()
    for i in range(10):
        store.submit(f"Team {i}", score=float(i * 10))

    board = store.get_leaderboard(limit=3)
    assert len(board) == 3
    # Top 3 should have the highest scores
    assert board[0].score == 90.0


def test_clear_leaderboard():
    """clear() should empty the leaderboard."""
    store = LeaderboardStore()
    store.submit("Team A", score=80.0)
    store.submit("Team B", score=90.0)
    assert len(store.get_leaderboard()) == 2

    store.clear()
    assert len(store.get_leaderboard()) == 0
    assert store.get_team("Team A") is None


def test_get_nonexistent_team():
    """Getting a non-existent team should return None."""
    store = LeaderboardStore()
    assert store.get_team("Ghost") is None


def test_badges_submitted_via_store():
    """Badges should be included in the entry when submitted via store."""
    store = LeaderboardStore()
    entry = store.submit("Champions", score=96.0, security_score=95.0)
    assert "slo_champion" in entry.badges
    assert "security_ace" in entry.badges
    assert "first_steps" in entry.badges
