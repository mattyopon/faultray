"""Architecture Git Diff Tracker for FaultRay.

Track infrastructure changes over git history by analyzing how the
infrastructure model file changes across commits.

Usage:
    from faultray.integrations.git_tracker import GitArchitectureTracker
    tracker = GitArchitectureTracker(repo_path, model_file="faultray-model.yaml")
    changes = tracker.track_history(commits=20)
    regression = tracker.find_regression_commit()
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ArchitectureChange:
    """A single architecture change captured from a git commit."""

    commit_hash: str
    commit_date: str
    commit_message: str
    components_added: list[str] = field(default_factory=list)
    components_removed: list[str] = field(default_factory=list)
    dependencies_added: int = 0
    dependencies_removed: int = 0
    score_before: float = 0.0
    score_after: float = 0.0
    score_delta: float = 0.0
    regression: bool = False
    component_count: int = 0
    dependency_count: int = 0


class GitArchitectureTracker:
    """Track infrastructure architecture changes across git history.

    Reads the model file from each commit in git history, loads the
    infrastructure graph, computes the resilience score, and identifies
    changes and potential regressions.
    """

    def __init__(
        self,
        repo_path: Path | str,
        model_file: str = "faultray-model.yaml",
    ) -> None:
        """Initialize the tracker.

        Args:
            repo_path: Path to the git repository root.
            model_file: Relative path to the infrastructure model file
                        within the repository.
        """
        self.repo_path = Path(repo_path)
        self.model_file = model_file
        self._validate_repo()

    def _validate_repo(self) -> None:
        """Check that repo_path is a valid git repository."""
        if not self.repo_path.exists():
            raise ValueError(
                f"'{self.repo_path}' is not a git repository."
            )

        git_dir = self.repo_path / ".git"
        if not git_dir.exists() and not git_dir.is_dir():
            # Also check if it's a worktree or submodule
            try:
                result = self._git_cmd(["rev-parse", "--git-dir"])
                if result.returncode != 0:
                    raise ValueError(
                        f"'{self.repo_path}' is not a git repository."
                    )
            except FileNotFoundError:
                raise ValueError(
                    "git is not installed or not in PATH."
                )

    def track_history(self, commits: int = 20) -> list[ArchitectureChange]:
        """Analyze infrastructure changes across recent git commits.

        For each commit that modified the model file:
        1. Load the model at that commit
        2. Compare with the previous version
        3. Compute score delta

        Args:
            commits: Maximum number of commits to analyze.

        Returns:
            List of ArchitectureChange objects, newest first.
        """
        # Get commits that touched the model file
        commit_hashes = self._get_commits_touching_model(commits)
        if not commit_hashes:
            logger.info("No commits found that modify '%s'", self.model_file)
            return []

        changes: list[ArchitectureChange] = []
        prev_components: set[str] | None = None
        prev_dep_count: int | None = None
        prev_score: float | None = None

        # Process from oldest to newest for correct delta calculation
        for commit_hash in reversed(commit_hashes):
            commit_info = self._get_commit_info(commit_hash)
            model_content = self._get_file_at_commit(commit_hash)

            if model_content is None:
                # File was deleted in this commit
                change = ArchitectureChange(
                    commit_hash=commit_hash,
                    commit_date=commit_info.get("date", ""),
                    commit_message=commit_info.get("message", ""),
                    components_removed=sorted(prev_components) if prev_components else [],
                    dependencies_removed=prev_dep_count or 0,
                    score_before=prev_score or 0.0,
                    score_after=0.0,
                    score_delta=-(prev_score or 0.0),
                    regression=True if prev_score and prev_score > 0 else False,
                )
                changes.append(change)
                prev_components = None
                prev_dep_count = None
                prev_score = None
                continue

            # Load the graph from this commit's model content
            graph_info = self._load_graph_from_content(model_content)
            if graph_info is None:
                logger.warning(
                    "Failed to parse model at commit %s", commit_hash[:8]
                )
                continue

            current_components, dep_count, current_score = graph_info

            # Compute deltas
            if prev_components is not None:
                added = sorted(current_components - prev_components)
                removed = sorted(prev_components - current_components)
                deps_added = max(0, dep_count - (prev_dep_count or 0))
                deps_removed = max(0, (prev_dep_count or 0) - dep_count)
                score_delta = current_score - (prev_score or 0.0)
            else:
                added = sorted(current_components)
                removed = []
                deps_added = dep_count
                deps_removed = 0
                score_delta = 0.0

            change = ArchitectureChange(
                commit_hash=commit_hash,
                commit_date=commit_info.get("date", ""),
                commit_message=commit_info.get("message", ""),
                components_added=added,
                components_removed=removed,
                dependencies_added=deps_added,
                dependencies_removed=deps_removed,
                score_before=prev_score if prev_score is not None else current_score,
                score_after=current_score,
                score_delta=round(score_delta, 2),
                regression=score_delta < -1.0,  # More than 1 point drop
                component_count=len(current_components),
                dependency_count=dep_count,
            )
            changes.append(change)

            prev_components = current_components
            prev_dep_count = dep_count
            prev_score = current_score

        # Return newest first
        changes.reverse()
        return changes

    def find_regression_commit(self) -> ArchitectureChange | None:
        """Find the commit that caused the biggest resilience score drop.

        Returns:
            The ArchitectureChange with the largest negative score_delta,
            or None if no regressions were found.
        """
        changes = self.track_history(commits=50)
        regressions = [c for c in changes if c.regression]
        if not regressions:
            return None

        # Return the one with the biggest drop
        return min(regressions, key=lambda c: c.score_delta)

    def get_current_score(self) -> float:
        """Get the resilience score of the current model file.

        Returns:
            The resilience score, or 0.0 if the model cannot be loaded.
        """
        model_path = self.repo_path / self.model_file
        if not model_path.exists():
            return 0.0

        content = model_path.read_text(encoding="utf-8")
        info = self._load_graph_from_content(content)
        if info is None:
            return 0.0
        return info[2]

    # ---- Git Helpers ----

    def _git_cmd(self, args: list[str]) -> subprocess.CompletedProcess:
        """Run a git command in the repository directory."""
        return subprocess.run(
            ["git"] + args,
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _get_commits_touching_model(self, max_commits: int) -> list[str]:
        """Get commit hashes that modified the model file."""
        result = self._git_cmd([
            "log",
            f"--max-count={max_commits}",
            "--format=%H",
            "--",
            self.model_file,
        ])

        if result.returncode != 0:
            logger.warning("git log failed: %s", result.stderr.strip())
            return []

        hashes = [h.strip() for h in result.stdout.strip().split("\n") if h.strip()]
        return hashes

    def _get_commit_info(self, commit_hash: str) -> dict[str, str]:
        """Get metadata for a specific commit."""
        result = self._git_cmd([
            "log",
            "-1",
            "--format=%ai|%s",
            commit_hash,
        ])

        if result.returncode != 0:
            return {"date": "", "message": ""}

        parts = result.stdout.strip().split("|", 1)
        return {
            "date": parts[0] if len(parts) > 0 else "",
            "message": parts[1] if len(parts) > 1 else "",
        }

    def _get_file_at_commit(self, commit_hash: str) -> str | None:
        """Get the content of the model file at a specific commit."""
        result = self._git_cmd([
            "show",
            f"{commit_hash}:{self.model_file}",
        ])

        if result.returncode != 0:
            # File might not exist in this commit
            return None

        return result.stdout

    def _load_graph_from_content(
        self, content: str,
    ) -> tuple[set[str], int, float] | None:
        """Load an InfraGraph from model file content.

        Returns:
            Tuple of (component_ids, dependency_count, resilience_score),
            or None if parsing fails.
        """
        try:
            # Try YAML first (most common)
            import yaml
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                # Try JSON
                data = json.loads(content)
        except Exception:
            try:
                data = json.loads(content)
            except Exception:
                return None

        if not isinstance(data, dict):
            return None

        try:
            from faultray.model.components import Component, Dependency
            from faultray.model.graph import InfraGraph

            graph = InfraGraph()

            for c in data.get("components", []):
                if isinstance(c, dict):
                    try:
                        graph.add_component(Component(**c))
                    except Exception:
                        # Skip malformed components
                        continue

            dep_count = 0
            for d in data.get("dependencies", []):
                if isinstance(d, dict):
                    try:
                        # Handle YAML format (source/target) vs JSON (source_id/target_id)
                        if "source" in d and "source_id" not in d:
                            d = dict(d)
                            d["source_id"] = d.pop("source")
                            d["target_id"] = d.pop("target")
                            if "type" in d and "dependency_type" not in d:
                                d["dependency_type"] = d.pop("type")
                        graph.add_dependency(Dependency(**d))
                        dep_count += 1
                    except Exception:
                        continue

            component_ids = set(graph.components.keys())
            score = graph.resilience_score()
            return component_ids, dep_count, score

        except Exception as e:
            logger.warning("Failed to build graph: %s", e)
            return None
