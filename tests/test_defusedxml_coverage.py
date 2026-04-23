"""Regression: block unsafe stdlib `xml.*` parser imports (#91).

v11.2.0 migrated all XML parsing to defusedxml to close XXE / Billion
Laughs vectors. This test guards against regressions — a future commit
accidentally reintroducing `xml.etree.ElementTree.parse` / `.fromstring`
or `xml.sax.make_parser` would silently reopen the attack surface.

Allowlist (legitimate non-parsing uses):
  - xml.etree.ElementTree.Element  (type-annotation only, no parser)
  - xml.sax.saxutils.escape         (pure string escape helper)
  - xml.sax.saxutils.quoteattr      (pure string escape helper)

Anything else from `xml.*` is considered unsafe by default.
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src" / "faultray"

_ALLOWED_IMPORTS: set[str] = {
    # Pattern -> rationale (for maintainer review if this test fires).
    "from xml.etree.ElementTree import Element as _XMLElement",
    "from xml.sax.saxutils import escape",
    "from xml.sax.saxutils import escape as _xml_escape",
}

_XML_IMPORT_RE = re.compile(r"^(?:from|import)\s+xml(?:\.|$|\s)", re.MULTILINE)


def _python_files():
    return list(_SRC.rglob("*.py"))


def test_no_unsafe_xml_imports_in_src():
    """All `xml.*` imports in src/ must appear in the allowlist."""
    offenders: list[tuple[Path, str]] = []
    for py in _python_files():
        text = py.read_text(encoding="utf-8")
        for m in _XML_IMPORT_RE.finditer(text):
            # Extract the full line so we can match against the allowlist.
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.start())
            if line_end == -1:
                line_end = len(text)
            line = text[line_start:line_end].strip()
            # Skip comments (e.g. in docstrings)
            if line.startswith("#"):
                continue
            if line not in _ALLOWED_IMPORTS:
                offenders.append((py.relative_to(_SRC.parent), line))

    if offenders:
        lines = "\n".join(f"  {p}: {l}" for p, l in offenders)
        raise AssertionError(
            "unsafe stdlib xml.* imports detected (use defusedxml instead, "
            "or add to _ALLOWED_IMPORTS if a non-parsing use):\n" + lines
        )


def test_defusedxml_is_pinned_in_dependencies():
    """defusedxml must stay in pyproject.toml runtime deps."""
    import tomllib

    pyproject = _SRC.parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    deps = data["project"]["dependencies"]
    assert any(d.startswith("defusedxml") for d in deps), (
        "defusedxml must remain in [project].dependencies to preserve "
        "the XXE / Billion-Laughs hardening done in v11.2.0 (#91)"
    )
