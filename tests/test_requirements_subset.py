"""Lock in the requirements.txt <-> pyproject.toml contract (#85).

requirements.txt is the Streamlit Cloud deployment manifest only. Every
dep listed there must also be declared in pyproject.toml, otherwise we
have drift that will bite us in the Streamlit Cloud build.

(The reverse is NOT required — pyproject.toml has server-side deps that
aren't needed for the Streamlit UI.)
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _parse_requirements(path: Path) -> set[str]:
    pkgs: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # strip version spec: "streamlit>=1.35.0" -> "streamlit"
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.\-]*)", line)
        if m:
            pkgs.add(m.group(1).lower().replace("_", "-"))
    return pkgs


def _parse_pyproject_deps(path: Path) -> set[str]:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    deps: list[str] = data["project"].get("dependencies", [])
    out: set[str] = set()
    for raw in deps:
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.\-]*)", raw)
        if m:
            out.add(m.group(1).lower().replace("_", "-"))
    # Optional deps (project.optional-dependencies.*) also count
    for _group, entries in (data["project"].get("optional-dependencies", {}) or {}).items():
        for raw in entries:
            m = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.\-]*)", raw)
            if m:
                out.add(m.group(1).lower().replace("_", "-"))
    return out


def test_requirements_txt_is_subset_of_pyproject():
    """Every dep in requirements.txt must also live in pyproject.toml."""
    req = _parse_requirements(_PROJECT_ROOT / "requirements.txt")
    pyp = _parse_pyproject_deps(_PROJECT_ROOT / "pyproject.toml")
    missing = req - pyp
    assert not missing, (
        f"requirements.txt drifted from pyproject.toml — these deps are "
        f"listed in requirements.txt but NOT declared in pyproject.toml: "
        f"{sorted(missing)}. Add them to pyproject.toml first, then mirror "
        f"here only if the Streamlit UI actually imports them at runtime."
    )


def test_requirements_txt_documents_its_purpose():
    """Guard against 'just delete the comments' regressions."""
    text = (_PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "Streamlit Cloud" in text, (
        "requirements.txt must document that it is the Streamlit Cloud "
        "manifest (see #85). pyproject.toml is the canonical dep source."
    )
    assert "pyproject.toml" in text, (
        "requirements.txt comment must point developers at pyproject.toml "
        "for local dev."
    )
