"""Lightweight CI guards that lock in the security quick-win fixes.

These run as part of the normal pytest suite (no separate workflow) and are
designed to PASS on the current tree while failing if a fix is reverted —
e.g. a sensitive integrity file dropping back to an unkeyed hash, or a CSV
exporter bypassing the formula-injection neutralizer. They are intentionally
file-scoped (not a blanket ban) so they do not break on unrelated existing code.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from faultray.model.components import Component, ComponentType

SRC = Path(__file__).resolve().parents[1] / "src" / "faultray"


# ---------------------------------------------------------------------------
# Component model-boundary validator (XSS / report-injection)
# ---------------------------------------------------------------------------

def _component(**kw) -> Component:
    base = dict(id="svc-1", name="Web", type=ComponentType.WEB_SERVER)
    base.update(kw)
    return Component(**base)


@pytest.mark.parametrize("field", ["id", "name", "host", "owner"])
@pytest.mark.parametrize("payload", [
    "<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "a>b",
    "x<svg/onload=1>", "line1\r\nline2", "tab\tinject", "nul\x00byte",
])
def test_component_rejects_injection_chars(field: str, payload: str) -> None:
    with pytest.raises(ValidationError):
        _component(**{field: payload})


@pytest.mark.parametrize("name", [
    "CloudFront CDN", "PostgreSQL (User Data)", "Auth & Billing",
    "O'Brien's DB", 'say "hi" svc', "db-primary_01",
])
def test_component_accepts_legitimate_names(name: str) -> None:
    assert _component(name=name).name == name


# ---------------------------------------------------------------------------
# Integrity primitives must be keyed in sensitive files
# ---------------------------------------------------------------------------

def test_sensitive_integrity_files_using_sha256_also_use_hmac() -> None:
    """Audit/seal/license files that hash with sha256 must also use hmac, so a
    tamper-evidence / signing primitive is never shipped unkeyed."""
    offenders = []
    for path in SRC.rglob("*.py"):
        if not re.search(r"audit|seal|licens|coupon", path.name, re.I):
            continue
        text = path.read_text(encoding="utf-8")
        if "hashlib.sha256" in text and "hmac" not in text:
            offenders.append(str(path.relative_to(SRC)))
    assert not offenders, f"unkeyed sha256 in sensitive file(s): {offenders}"


def test_audit_chain_links_are_hmac_keyed() -> None:
    text = (SRC / "reporter" / "audit_chain.py").read_text(encoding="utf-8")
    assert "hmac.new(" in text
    assert "compare_digest" in text


# ---------------------------------------------------------------------------
# CSV exporters must route through the formula-injection neutralizer
# ---------------------------------------------------------------------------

def test_all_csv_writers_use_neutralizer() -> None:
    """EVERY module that writes CSV (csv.writer / csv.DictWriter) must route its
    cells through the csv_safe neutralizer — otherwise a user/overlay-derived
    value starting with =,+,-,@ becomes a live spreadsheet formula on open
    (CSV injection, CWE-1236). This enumerates all writers so a NEW unguarded
    exporter is caught automatically, not just a hand-maintained list."""
    offenders = []
    for path in SRC.rglob("*.py"):
        if path.name == "csv_safe.py":
            continue
        text = path.read_text(encoding="utf-8")
        if ("csv.writer(" in text or "csv.DictWriter(" in text) and "csv_safe" not in text:
            offenders.append(str(path.relative_to(SRC)))
    assert not offenders, f"CSV writer(s) not routed through csv_safe: {offenders}"


# ---------------------------------------------------------------------------
# Every subprocess call must carry a timeout (no hung children)
# ---------------------------------------------------------------------------

_SUBPROCESS_FUNCS = {"run", "call", "check_call", "check_output", "Popen"}


def _subprocess_calls_without_timeout() -> list[str]:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"
                and func.attr in _SUBPROCESS_FUNCS
            ):
                if "timeout" not in {kw.arg for kw in node.keywords}:
                    offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
    return offenders


def test_no_subprocess_call_without_timeout() -> None:
    """A subprocess without timeout= can hang a worker/agent forever. Every
    call in src/ must pass timeout= (the autonomous agent routes apply/destroy
    through _apply_guarded which enforces it)."""
    offenders = _subprocess_calls_without_timeout()
    assert not offenders, f"subprocess call(s) missing timeout=: {offenders}"


# ---------------------------------------------------------------------------
# CI workflow: PR infra-file selection must not SIGPIPE-abort under pipefail,
# nor be disabled when the first match has an unsafe (crafted) filename
# ---------------------------------------------------------------------------

def test_pr_check_selects_yaml_safely() -> None:
    """faultray-pr-check.yml must NOT pick the infra YAML with `find | head`:
    under `set -o pipefail`, head closing the pipe after one line kills find
    with SIGPIPE (exit 141) on PRs with many matches, aborting the whole gate.
    It must iterate `find -print0` NUL-delimited (process substitution keeps
    find off the foreground pipeline) and SKIP unsafe filenames rather than
    surrendering the scan when the first match happens to be unsafe."""
    wf = (
        Path(__file__).resolve().parents[1]
        / ".github" / "workflows" / "faultray-pr-check.yml"
    )
    text = wf.read_text(encoding="utf-8")
    # Strip full-line comments (YAML or shell `#`) so the guard inspects the
    # actual commands, not the explanatory prose that names the bad pattern.
    code = "\n".join(
        ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
    )
    assert "-print0" in code, "PR-check must read find output NUL-delimited (-print0)"
    assert not re.search(r"find\b[^\n|]*\|\s*head", code), (
        "PR-check selects files with `find | head` — SIGPIPE-aborts under "
        "pipefail on many-file PRs; use a `find -print0` loop instead"
    )
