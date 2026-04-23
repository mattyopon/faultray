# DORA evidence module split (#88)

This directory was converted from the monolithic
`simulator/dora_evidence.py` (2630 lines) to a package so the
contents can be extracted into focused submodules over several PRs
**without breaking import paths**.

## Current state (phase 1 — container only)
All symbols still live in `__init__.py`. Downstream callers using
`from faultray.simulator.dora_evidence import DORAArticle, ...` keep
working unchanged.

## Planned split (phase 2+, follow-up PRs)

| Submodule | Contents | Approx LOC |
|---|---|---|
| `models.py` | enums (DORAArticle, DORAPillar, ...) + Pydantic models + RiskConfig | ~200 |
| `articles.py` | `_ARTICLE_PILLAR_MAP` + article-to-pillar lookup | ~50 |
| `controls.py` | `_build_controls()` + 28 DORAControl static definitions | ~650 |
| `evaluators/` | One file per DORA article (Art. 5, 6, 7, ..., 45) | ~50 each |
| `engine.py` | `DORAEvidenceEngine` orchestrating the evaluators | ~400 |
| `__init__.py` | Thin re-export shim so public API is stable | ~30 |

Each extraction PR will move **one section** at a time, run
`pytest tests/test_dora_*.py` + `mypy --strict src/faultray/model/`, and
preserve test pass count. A single mega-PR would be high-risk for
import cycles.

## Why the gallery.py split is separate

`src/faultray/templates/gallery.py` (2053 lines) has a similar
oversized shape. A parallel package conversion is tracked in the same
Issue (#88). Doing both in one PR amplifies review complexity, so
that split is queued for a follow-up.
