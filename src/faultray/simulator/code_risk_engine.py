# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Code Risk Simulation Engine.

Analyzes PR diffs and code changes to predict:
1. Runtime performance impact (CPU, memory, I/O changes)
2. AI hallucination risk (probability of AI-generated bugs)
3. Infrastructure cascade impact (how code changes affect infra components)

This extends FaultRay's graph-based simulation from infrastructure-only
to cross-layer (code + infrastructure) risk analysis.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..model.code_components import (
    AuthorType,
    CodeComponent,
    CodeLanguage,
    ComplexityClass,
    DiffImpact,
    HallucinationRiskProfile,
    RuntimeCostProfile,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# AI co-author patterns in git commits
_AI_AUTHOR_PATTERNS: dict[str, AuthorType] = {
    "claude": AuthorType.AI_CLAUDE,
    "anthropic": AuthorType.AI_CLAUDE,
    "copilot": AuthorType.AI_COPILOT,
    "gpt": AuthorType.AI_GPT,
    "openai": AuthorType.AI_GPT,
    "codex": AuthorType.AI_CODEX,
    "cursor": AuthorType.AI_CURSOR,
}

# Complexity heuristics (regex patterns → estimated complexity)
_COMPLEXITY_PATTERNS: list[tuple[str, ComplexityClass, float]] = [
    # Nested loops → O(n²)
    (r"for\s+.+:\s*\n\s+for\s+", ComplexityClass.O_N2, 5.0),
    # Triple nested → O(n³)
    (r"for\s+.+:\s*\n\s+for\s+.+:\s*\n\s+for\s+", ComplexityClass.O_N3, 50.0),
    # Recursive calls without memoization
    (r"def\s+(\w+)\(.*\).*:\s*\n(?:.*\n)*?\s+\1\(", ComplexityClass.O_2N, 100.0),
    # Sort operations
    (r"\.sort\(|sorted\(", ComplexityClass.O_N_LOG_N, 2.0),
    # Simple iteration
    (r"for\s+\w+\s+in\s+", ComplexityClass.O_N, 1.0),
]

# Hallucination risk patterns
_HALLUCINATION_PATTERNS: list[tuple[str, str, float]] = [
    # Calls to APIs that commonly don't exist
    (r"\.\w+_async\(", "uses_nonexistent_api", 0.1),
    # Bare except (often AI-generated mistake)
    (r"except:\s*$", "incorrect_error_handling", 0.15),
    # except Exception as e: pass (swallowed error)
    (r"except\s+\w+.*:\s*\n\s+pass", "incorrect_error_handling", 0.2),
    # Magic numbers (AI often hallucinates arbitrary values)
    (r"=\s*(?:42|100|1000|9999|12345)\s*[;\n#]", "wrong_argument_order", 0.05),
    # TODO/FIXME left by AI
    (r"#\s*(?:TODO|FIXME|HACK|XXX)", "stale_dependency", 0.05),
]

# Base hallucination rates by author type.
# DISCLAIMER: These are estimated rates based on informal benchmarks and
# industry observations, NOT peer-reviewed measurements. They serve as
# relative priors for risk ranking (Claude < GPT < Copilot), not as
# absolute probabilities. Adjust via config if you have project-specific data.
_BASE_HALLUCINATION_RATES: dict[AuthorType, float] = {
    AuthorType.HUMAN: 0.01,
    AuthorType.AI_CLAUDE: 0.03,
    AuthorType.AI_GPT: 0.05,
    AuthorType.AI_COPILOT: 0.07,
    AuthorType.AI_CODEX: 0.06,
    AuthorType.AI_CURSOR: 0.04,
    AuthorType.AI_UNKNOWN: 0.08,
    AuthorType.MIXED: 0.04,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CodeRiskReport:
    """Complete risk assessment for a code change (PR/commit)."""

    diff_impacts: list[DiffImpact] = field(default_factory=list)
    code_components: list[CodeComponent] = field(default_factory=list)

    # Aggregate scores
    total_cpu_delta_ms: float = 0.0
    total_memory_delta_mb: float = 0.0
    total_io_delta: int = 0
    max_hallucination_risk: float = 0.0
    overall_risk_score: float = 0.0

    # Risk breakdown
    regressions: list[DiffImpact] = field(default_factory=list)
    high_risk_files: list[str] = field(default_factory=list)
    ai_authored_files: list[str] = field(default_factory=list)

    # Recommendations
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON output."""
        return {
            "overall_risk_score": round(self.overall_risk_score, 4),
            "max_hallucination_risk": round(self.max_hallucination_risk, 4),
            "performance_impact": {
                "cpu_delta_ms": round(self.total_cpu_delta_ms, 2),
                "memory_delta_mb": round(self.total_memory_delta_mb, 2),
                "io_delta": self.total_io_delta,
            },
            "files_analyzed": len(self.diff_impacts),
            "regressions": len(self.regressions),
            "high_risk_files": self.high_risk_files,
            "ai_authored_files": self.ai_authored_files,
            "recommendations": self.recommendations,
            "details": [
                {
                    "file": d.file_path,
                    "language": d.language.value,
                    "lines_added": d.lines_added,
                    "lines_removed": d.lines_removed,
                    "complexity_change": f"{d.complexity_before.value} → {d.complexity_after.value}",
                    "cpu_delta_ms": round(d.cpu_delta_ms, 2),
                    "memory_delta_mb": round(d.memory_delta_mb, 2),
                    "hallucination_risk": round(d.hallucination_risk.composite_risk, 4),
                    "author_type": d.hallucination_risk.author_type.value,
                    "is_regression": d.is_regression,
                }
                for d in self.diff_impacts
            ],
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class CodeRiskEngine:
    """Analyzes code changes for runtime risk and AI hallucination probability.

    Usage::

        engine = CodeRiskEngine(repo_path="/path/to/repo")
        report = engine.analyze_diff("main", "feature-branch")
        print(report.overall_risk_score)
    """

    def __init__(self, repo_path: str | Path = ".") -> None:
        self.repo_path = Path(repo_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_diff(
        self,
        base_ref: str = "main",
        head_ref: str = "HEAD",
    ) -> CodeRiskReport:
        """Analyze the diff between two git refs and produce a risk report.

        Args:
            base_ref: Base branch/commit (e.g., "main")
            head_ref: Head branch/commit (e.g., "HEAD", "feature-branch")

        Returns:
            CodeRiskReport with per-file and aggregate risk scores.
        """
        diff_text = self._get_git_diff(base_ref, head_ref)
        if not diff_text:
            return CodeRiskReport()

        file_diffs = self._parse_diff(diff_text)
        commit_authors = self._get_commit_authors(base_ref, head_ref)

        report = CodeRiskReport()

        # Get base ref file contents for cost_before calculation
        base_file_contents = self._get_base_file_contents(base_ref, [f[0] for f in file_diffs])

        for file_path, added_lines, removed_lines, added_content, removed_content in file_diffs:
            language = self._detect_language(file_path)
            if language == CodeLanguage.UNKNOWN:
                continue  # Skip non-code files

            author_type = self._detect_ai_author(file_path, commit_authors)

            # Analyze the added code (new state)
            complexity_after = self._estimate_complexity(added_content)
            cost_after = self._estimate_runtime_cost(added_content, language, complexity_after)

            # Analyze the removed code + base file (old state)
            base_content = base_file_contents.get(file_path, "")
            complexity_before = self._estimate_complexity(base_content) if base_content else ComplexityClass.UNKNOWN
            cost_before = self._estimate_runtime_cost(base_content, language, complexity_before) if base_content else RuntimeCostProfile()

            hallucination = self._assess_hallucination_risk(
                added_content, author_type, file_path
            )

            impact = DiffImpact(
                file_path=file_path,
                language=language,
                lines_added=added_lines,
                lines_removed=removed_lines,
                complexity_before=complexity_before,
                complexity_after=complexity_after,
                cost_before=cost_before,
                cost_after=cost_after,
                hallucination_risk=hallucination,
            )

            report.diff_impacts.append(impact)

            # Aggregate
            report.total_cpu_delta_ms += impact.cpu_delta_ms
            report.total_memory_delta_mb += impact.memory_delta_mb
            report.total_io_delta += impact.io_delta

            if hallucination.composite_risk > report.max_hallucination_risk:
                report.max_hallucination_risk = hallucination.composite_risk

            if impact.is_regression:
                report.regressions.append(impact)

            if hallucination.composite_risk > 0.1:
                report.high_risk_files.append(file_path)

            if author_type != AuthorType.HUMAN:
                report.ai_authored_files.append(file_path)

        # Calculate overall risk score
        report.overall_risk_score = self._calculate_overall_risk(report)

        # Generate recommendations
        report.recommendations = self._generate_recommendations(report)

        return report

    def analyze_file(self, file_path: str | Path) -> CodeComponent:
        """Analyze a single file and return its CodeComponent model."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        content = path.read_text(encoding="utf-8", errors="replace")
        language = self._detect_language(str(path))
        complexity = self._estimate_complexity(content)
        cost = self._estimate_runtime_cost(content, language, complexity)

        return CodeComponent(
            id=str(path),
            name=path.name,
            file_path=str(path),
            language=language,
            runtime_cost=cost,
        )

    # ------------------------------------------------------------------
    # Git operations
    # ------------------------------------------------------------------

    def _get_git_diff(self, base_ref: str, head_ref: str) -> str:
        """Get git diff between two refs."""
        try:
            result = subprocess.run(
                ["git", "diff", f"{base_ref}...{head_ref}", "--unified=3"],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=30,
            )
            return result.stdout
        except (subprocess.SubprocessError, FileNotFoundError):
            return ""

    def _get_base_file_contents(self, base_ref: str, file_paths: list[str]) -> dict[str, str]:
        """Get file contents at the base ref for cost_before calculation."""
        contents: dict[str, str] = {}
        for fp in file_paths:
            try:
                result = subprocess.run(
                    ["git", "show", f"{base_ref}:{fp}"],
                    capture_output=True,
                    text=True,
                    cwd=self.repo_path,
                    timeout=10,
                )
                if result.returncode == 0:
                    contents[fp] = result.stdout
            except (subprocess.SubprocessError, FileNotFoundError):
                pass  # New file — no base content
        return contents

    def _get_commit_authors(self, base_ref: str, head_ref: str) -> dict[str, list[str]]:
        """Get commit messages for author detection.

        Returns dict mapping file paths to list of commit messages that touched them.
        """
        try:
            result = subprocess.run(
                [
                    "git", "log", f"{base_ref}...{head_ref}",
                    "--name-only", "--format=%B---COMMIT_SEP---",
                ],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=30,
            )
            output = result.stdout
        except (subprocess.SubprocessError, FileNotFoundError):
            return {}

        file_messages: dict[str, list[str]] = {}
        commits = output.split("---COMMIT_SEP---")
        for commit in commits:
            lines = commit.strip().split("\n")
            message_lines = []
            file_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                # File paths don't contain spaces (usually) and exist on disk
                if "/" in stripped or stripped.endswith((".py", ".ts", ".tsx", ".js", ".go", ".rs")):
                    file_lines.append(stripped)
                else:
                    message_lines.append(stripped)
            message = " ".join(message_lines)
            for f in file_lines:
                if f not in file_messages:
                    file_messages[f] = []
                file_messages[f].append(message)

        return file_messages

    # ------------------------------------------------------------------
    # Diff parsing
    # ------------------------------------------------------------------

    def _parse_diff(self, diff_text: str) -> list[tuple[str, int, int, str, str]]:
        """Parse unified diff into (file_path, lines_added, lines_removed, added_content, removed_content).

        Handles:
        - Binary files (skipped — 0 lines)
        - Renamed files (uses new path)
        - File paths with spaces
        """
        files: list[tuple[str, int, int, str, str]] = []
        current_file = ""
        is_binary = False
        added = 0
        removed = 0
        added_lines: list[str] = []
        removed_lines: list[str] = []

        for line in diff_text.split("\n"):
            if line.startswith("diff --git"):
                if current_file and not is_binary:
                    files.append((current_file, added, removed, "\n".join(added_lines), "\n".join(removed_lines)))
                # Extract file path: diff --git a/path b/path
                # Handle paths with spaces by splitting on " b/"
                parts = line.split(" b/", 1)
                current_file = parts[-1] if len(parts) > 1 else ""
                is_binary = False
                added = 0
                removed = 0
                added_lines = []
                removed_lines = []
            elif line.startswith("Binary files"):
                is_binary = True
            elif line.startswith("rename to "):
                # Handle renames: use the new path
                current_file = line[len("rename to "):]
            elif not is_binary:
                if line.startswith("+") and not line.startswith("+++"):
                    added += 1
                    added_lines.append(line[1:])
                elif line.startswith("-") and not line.startswith("---"):
                    removed += 1
                    removed_lines.append(line[1:])

        if current_file and not is_binary:
            files.append((current_file, added, removed, "\n".join(added_lines), "\n".join(removed_lines)))

        return files

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _detect_language(self, file_path: str) -> CodeLanguage:
        """Detect programming language from file extension."""
        ext_map = {
            ".py": CodeLanguage.PYTHON,
            ".ts": CodeLanguage.TYPESCRIPT,
            ".tsx": CodeLanguage.TYPESCRIPT,
            ".js": CodeLanguage.JAVASCRIPT,
            ".jsx": CodeLanguage.JAVASCRIPT,
            ".go": CodeLanguage.GO,
            ".rs": CodeLanguage.RUST,
            ".java": CodeLanguage.JAVA,
        }
        for ext, lang in ext_map.items():
            if file_path.endswith(ext):
                return lang
        return CodeLanguage.UNKNOWN

    def _detect_ai_author(
        self, file_path: str, commit_messages: dict[str, list[str]]
    ) -> AuthorType:
        """Detect if file was authored by AI from commit messages."""
        messages = commit_messages.get(file_path, [])
        full_text = " ".join(messages).lower()

        for pattern, author_type in _AI_AUTHOR_PATTERNS.items():
            if pattern in full_text:
                return author_type

        # Check for Co-Authored-By header
        if "co-authored-by" in full_text:
            for pattern, author_type in _AI_AUTHOR_PATTERNS.items():
                if pattern in full_text:
                    return author_type
            return AuthorType.AI_UNKNOWN

        return AuthorType.HUMAN

    def _estimate_complexity(self, code: str) -> ComplexityClass:
        """Estimate algorithmic complexity from code patterns."""
        best = ComplexityClass.O_1
        best_weight = 0.0

        for pattern, complexity, weight in _COMPLEXITY_PATTERNS:
            if re.search(pattern, code, re.MULTILINE):
                if weight > best_weight:
                    best = complexity
                    best_weight = weight

        return best

    def _estimate_runtime_cost(
        self,
        code: str,
        language: CodeLanguage,
        complexity: ComplexityClass,
    ) -> RuntimeCostProfile:
        """Estimate runtime cost from code analysis."""
        # Language-specific base costs (ms per 1000 lines)
        language_base_cost = {
            CodeLanguage.PYTHON: 5.0,
            CodeLanguage.TYPESCRIPT: 2.0,
            CodeLanguage.JAVASCRIPT: 2.0,
            CodeLanguage.GO: 0.5,
            CodeLanguage.RUST: 0.3,
            CodeLanguage.JAVA: 1.0,
            CodeLanguage.UNKNOWN: 3.0,
        }

        # Complexity multipliers
        complexity_multiplier = {
            ComplexityClass.O_1: 1.0,
            ComplexityClass.O_LOG_N: 1.5,
            ComplexityClass.O_N: 2.0,
            ComplexityClass.O_N_LOG_N: 3.0,
            ComplexityClass.O_N2: 10.0,
            ComplexityClass.O_N3: 100.0,
            ComplexityClass.O_2N: 1000.0,
            ComplexityClass.UNKNOWN: 2.0,
        }

        lines = len(code.split("\n"))
        base = language_base_cost.get(language, 3.0)
        multiplier = complexity_multiplier.get(complexity, 2.0)

        cpu_ms = (lines / 1000) * base * multiplier
        memory_mb = lines * 0.001  # ~1KB per line as rough estimate

        # Count I/O patterns
        io_patterns = [
            r"\.query\(", r"\.execute\(", r"fetch\(", r"requests\.",
            r"\.get\(", r"\.post\(", r"open\(", r"\.read\(",
            r"supabase\.", r"prisma\.", r"cursor\.",
        ]
        io_calls = sum(len(re.findall(p, code)) for p in io_patterns)

        network_patterns = [
            r"fetch\(", r"requests\.", r"urllib", r"httpx\.",
            r"axios\.", r"\.get\(.*http", r"curl",
        ]
        network_calls = sum(len(re.findall(p, code)) for p in network_patterns)

        return RuntimeCostProfile(
            complexity=complexity,
            estimated_cpu_ms_per_call=round(cpu_ms, 2),
            estimated_peak_cpu_ms=round(cpu_ms * 3, 2),
            estimated_memory_mb_per_call=round(memory_mb, 2),
            estimated_peak_memory_mb=round(memory_mb * 2, 2),
            estimated_io_calls_per_invocation=io_calls,
            estimated_io_latency_ms=io_calls * 10.0,
            network_calls_per_invocation=network_calls,
            is_blocking=bool(re.search(r"time\.sleep\(|\.wait\(", code)),
            holds_lock=bool(re.search(r"Lock\(\)|acquire\(|synchronized", code)),
        )

    def _assess_hallucination_risk(
        self,
        code: str,
        author_type: AuthorType,
        file_path: str,
    ) -> HallucinationRiskProfile:
        """Assess hallucination risk for code."""
        base_rate = _BASE_HALLUCINATION_RATES.get(author_type, 0.05)

        profile = HallucinationRiskProfile(
            author_type=author_type,
            base_hallucination_risk=base_rate,
        )

        # Check for hallucination patterns
        for pattern, field_name, risk_increase in _HALLUCINATION_PATTERNS:
            if re.search(pattern, code, re.MULTILINE):
                current = getattr(profile, field_name, 0.0)
                setattr(profile, field_name, min(current + risk_increase, 1.0))

        # Check for test coverage
        test_file = file_path.replace("src/", "tests/test_").replace(".py", "_test.py")
        alt_test = file_path.replace("src/", "tests/test_")
        if (self.repo_path / test_file).exists() or (self.repo_path / alt_test).exists():
            profile.has_tests = True

        # Check for type hints (Python)
        if file_path.endswith(".py"):
            type_hint_count = len(re.findall(r":\s*\w+[\[\]|,\s]*(?:=|$|\))", code))
            total_functions = len(re.findall(r"def\s+\w+", code))
            if total_functions > 0 and type_hint_count / max(total_functions, 1) > 0.5:
                profile.type_checked = True

        return profile

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _calculate_overall_risk(self, report: CodeRiskReport) -> float:
        """Calculate overall risk score (0.0 - 1.0)."""
        if not report.diff_impacts:
            return 0.0

        # Performance risk (normalized)
        perf_risk = 0.0
        if report.total_cpu_delta_ms > 0:
            perf_risk = min(report.total_cpu_delta_ms / 100, 1.0)  # 100ms = max risk

        # AI risk (max across files)
        ai_risk = report.max_hallucination_risk

        # Scale risk (more files changed = more risk)
        scale_factor = min(len(report.diff_impacts) / 20, 1.0)  # 20+ files = max

        # Regression count
        regression_risk = min(len(report.regressions) / 5, 1.0)  # 5+ regressions = max

        # Weighted combination
        return min(
            perf_risk * 0.2
            + ai_risk * 0.4
            + scale_factor * 0.1
            + regression_risk * 0.3,
            1.0,
        )

    def _generate_recommendations(self, report: CodeRiskReport) -> list[str]:
        """Generate actionable recommendations."""
        recs = []

        if report.max_hallucination_risk > 0.15:
            recs.append(
                "HIGH AI RISK: AI-authored code has >15% hallucination probability. "
                "Require human review before merge."
            )

        if report.max_hallucination_risk > 0.05:
            ai_files = ", ".join(report.ai_authored_files[:5])
            recs.append(
                f"AI-authored files detected: {ai_files}. "
                "Run full test suite and verify API calls exist."
            )

        for impact in report.regressions:
            if impact.cpu_delta_ms > 10:
                recs.append(
                    f"PERF REGRESSION: {impact.file_path} adds "
                    f"+{impact.cpu_delta_ms:.1f}ms CPU per call. Profile before merge."
                )

        for impact in report.diff_impacts:
            if impact.hallucination_risk.incorrect_error_handling > 0:
                recs.append(
                    f"ERROR HANDLING: {impact.file_path} has suspicious error handling patterns. "
                    "Verify catch blocks are not swallowing errors."
                )
            if impact.cost_after.is_blocking:
                recs.append(
                    f"BLOCKING CODE: {impact.file_path} contains blocking operations "
                    "(sleep/wait). May cause event loop stalls."
                )

        if not recs:
            recs.append("No significant risks detected in this change.")

        return recs
