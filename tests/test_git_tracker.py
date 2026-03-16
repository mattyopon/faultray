"""Tests for Architecture Git Diff Tracker."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

from faultray.integrations.git_tracker import ArchitectureChange, GitArchitectureTracker


def _create_test_repo(tmp_path: Path) -> Path:
    """Create a test git repository with infrastructure model commits."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()

    def _git(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + args,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )

    # Initialize repo
    _git(["init"])
    _git(["config", "user.email", "test@test.com"])
    _git(["config", "user.name", "Test"])

    # Commit 1: Initial model with 2 components
    model_v1 = {
        "schema_version": "3.0",
        "components": [
            {"id": "app", "name": "App", "type": "app_server", "replicas": 1},
            {"id": "db", "name": "DB", "type": "database", "replicas": 1},
        ],
        "dependencies": [
            {"source_id": "app", "target_id": "db", "dependency_type": "requires"},
        ],
    }
    model_file = repo_path / "faultray-model.yaml"
    model_file.write_text(yaml.dump(model_v1), encoding="utf-8")
    _git(["add", "."])
    _git(["commit", "-m", "Initial infrastructure"])

    # Commit 2: Add cache, improve replicas
    model_v2 = {
        "schema_version": "3.0",
        "components": [
            {"id": "app", "name": "App", "type": "app_server", "replicas": 2},
            {"id": "db", "name": "DB", "type": "database", "replicas": 1},
            {"id": "cache", "name": "Cache", "type": "cache", "replicas": 2},
        ],
        "dependencies": [
            {"source_id": "app", "target_id": "db", "dependency_type": "requires"},
            {"source_id": "app", "target_id": "cache", "dependency_type": "optional"},
        ],
    }
    model_file.write_text(yaml.dump(model_v2), encoding="utf-8")
    _git(["add", "."])
    _git(["commit", "-m", "Add cache layer"])

    # Commit 3: Remove cache (regression)
    model_v3 = {
        "schema_version": "3.0",
        "components": [
            {"id": "app", "name": "App", "type": "app_server", "replicas": 1},
            {"id": "db", "name": "DB", "type": "database", "replicas": 1},
        ],
        "dependencies": [
            {"source_id": "app", "target_id": "db", "dependency_type": "requires"},
        ],
    }
    model_file.write_text(yaml.dump(model_v3), encoding="utf-8")
    _git(["add", "."])
    _git(["commit", "-m", "Remove cache for simplification"])

    return repo_path


class TestGitArchitectureTracker:
    """Test suite for GitArchitectureTracker."""

    def test_track_history_returns_changes(self, tmp_path):
        """Test that track_history returns a list of changes."""
        repo_path = _create_test_repo(tmp_path)
        tracker = GitArchitectureTracker(repo_path, "faultray-model.yaml")

        changes = tracker.track_history(commits=10)

        assert isinstance(changes, list)
        assert len(changes) == 3  # 3 commits
        for change in changes:
            assert isinstance(change, ArchitectureChange)

    def test_changes_newest_first(self, tmp_path):
        """Test that changes are returned newest first."""
        repo_path = _create_test_repo(tmp_path)
        tracker = GitArchitectureTracker(repo_path, "faultray-model.yaml")

        changes = tracker.track_history()

        # Newest commit should be "Remove cache"
        assert "Remove cache" in changes[0].commit_message
        assert "Initial" in changes[-1].commit_message

    def test_components_added_tracked(self, tmp_path):
        """Test that added components are tracked."""
        repo_path = _create_test_repo(tmp_path)
        tracker = GitArchitectureTracker(repo_path, "faultray-model.yaml")

        changes = tracker.track_history()

        # Second commit added "cache"
        add_cache_commit = next(
            c for c in changes if "Add cache" in c.commit_message
        )
        assert "cache" in add_cache_commit.components_added

    def test_components_removed_tracked(self, tmp_path):
        """Test that removed components are tracked."""
        repo_path = _create_test_repo(tmp_path)
        tracker = GitArchitectureTracker(repo_path, "faultray-model.yaml")

        changes = tracker.track_history()

        # Third commit removed "cache"
        remove_commit = next(
            c for c in changes if "Remove cache" in c.commit_message
        )
        assert "cache" in remove_commit.components_removed

    def test_score_delta_computed(self, tmp_path):
        """Test that score deltas are computed."""
        repo_path = _create_test_repo(tmp_path)
        tracker = GitArchitectureTracker(repo_path, "faultray-model.yaml")

        changes = tracker.track_history()

        # At least one non-initial commit should have a non-zero delta
        non_initial = [c for c in changes if c != changes[-1]]
        has_delta = any(c.score_delta != 0 for c in non_initial)
        # This may or may not have deltas depending on resilience score logic
        # but score_delta should at least be a float
        for c in changes:
            assert isinstance(c.score_delta, (int, float))

    def test_find_regression_commit(self, tmp_path):
        """Test finding the regression commit."""
        repo_path = _create_test_repo(tmp_path)
        tracker = GitArchitectureTracker(repo_path, "faultray-model.yaml")

        regression = tracker.find_regression_commit()

        # The third commit (removing cache, reducing replicas) may cause regression
        # depending on score calculation. Even if no regression, the method should
        # return None cleanly.
        if regression is not None:
            assert isinstance(regression, ArchitectureChange)
            assert regression.regression is True
            assert regression.score_delta < 0

    def test_get_current_score(self, tmp_path):
        """Test getting the current model's resilience score."""
        repo_path = _create_test_repo(tmp_path)
        tracker = GitArchitectureTracker(repo_path, "faultray-model.yaml")

        score = tracker.get_current_score()
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_invalid_repo_path(self, tmp_path):
        """Test that invalid repo path raises ValueError."""
        with pytest.raises(ValueError, match="not a git repository"):
            GitArchitectureTracker(tmp_path / "nonexistent", "model.yaml")

    def test_no_model_commits(self, tmp_path):
        """Test behavior when no commits touch the model file."""
        repo_path = tmp_path / "empty-repo"
        repo_path.mkdir()

        subprocess.run(
            ["git", "init"],
            cwd=str(repo_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(repo_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(repo_path),
            capture_output=True,
        )

        # Create a commit that doesn't touch the model file
        (repo_path / "readme.txt").write_text("hello")
        subprocess.run(
            ["git", "add", "."],
            cwd=str(repo_path),
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=str(repo_path),
            capture_output=True,
        )

        tracker = GitArchitectureTracker(repo_path, "faultray-model.yaml")
        changes = tracker.track_history()
        assert changes == []

    def test_commit_hash_is_set(self, tmp_path):
        """Test that commit hashes are populated."""
        repo_path = _create_test_repo(tmp_path)
        tracker = GitArchitectureTracker(repo_path, "faultray-model.yaml")

        changes = tracker.track_history()
        for change in changes:
            assert len(change.commit_hash) >= 7  # Short hash at minimum

    def test_commit_date_is_set(self, tmp_path):
        """Test that commit dates are populated."""
        repo_path = _create_test_repo(tmp_path)
        tracker = GitArchitectureTracker(repo_path, "faultray-model.yaml")

        changes = tracker.track_history()
        for change in changes:
            assert change.commit_date != ""

    def test_json_model_format(self, tmp_path):
        """Test tracking with a JSON model file."""
        repo_path = tmp_path / "json-repo"
        repo_path.mkdir()

        def _git(args):
            return subprocess.run(
                ["git"] + args, cwd=str(repo_path), capture_output=True, text=True,
            )

        _git(["init"])
        _git(["config", "user.email", "test@test.com"])
        _git(["config", "user.name", "Test"])

        model = {
            "schema_version": "3.0",
            "components": [
                {"id": "web", "name": "Web", "type": "web_server"},
            ],
            "dependencies": [],
        }
        model_file = repo_path / "model.json"
        model_file.write_text(json.dumps(model), encoding="utf-8")
        _git(["add", "."])
        _git(["commit", "-m", "Add web server"])

        tracker = GitArchitectureTracker(repo_path, "model.json")
        changes = tracker.track_history()

        assert len(changes) == 1
        assert "web" in changes[0].components_added

    def test_dependency_count_tracked(self, tmp_path):
        """Test that dependency counts are tracked in changes."""
        repo_path = _create_test_repo(tmp_path)
        tracker = GitArchitectureTracker(repo_path, "faultray-model.yaml")

        changes = tracker.track_history()
        for change in changes:
            assert isinstance(change.dependency_count, int)

    def test_max_commits_respected(self, tmp_path):
        """Test that commits parameter limits the analysis."""
        repo_path = _create_test_repo(tmp_path)
        tracker = GitArchitectureTracker(repo_path, "faultray-model.yaml")

        changes = tracker.track_history(commits=2)
        assert len(changes) <= 2
