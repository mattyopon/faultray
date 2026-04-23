"""Regression tests: prevent schema / OpenAPI version drift (#82, #101).

CHANGELOG announced schema v4.0, but init_cmd / gallery kept emitting
"3.0"; openapi_config also drifted to "10.3.0" while pyproject was at
11.2.0. This test locks both in sync.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    with open(_PROJECT_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def test_package_dunder_version_matches_pyproject():
    from faultray import __version__

    assert __version__ == _pyproject_version(), (
        f"__init__.__version__ ({__version__}) is out of sync with "
        f"pyproject.toml ({_pyproject_version()})"
    )


def test_openapi_config_reflects_package_version():
    from faultray import __version__
    from faultray.api.openapi_config import OPENAPI_CONFIG

    assert OPENAPI_CONFIG["version"] == __version__, (
        f"OPENAPI_CONFIG['version'] ({OPENAPI_CONFIG['version']}) must "
        f"reference faultray.__version__ ({__version__}) to prevent drift"
    )


def test_init_cmd_uses_schema_version_constant():
    """faultray init must emit SCHEMA_VERSION from model.components."""
    from faultray.model.components import SCHEMA_VERSION

    src = (_PROJECT_ROOT / "src/faultray/cli/init_cmd.py").read_text()
    # Must NOT contain hardcoded "schema_version": "3.0"
    assert '"schema_version": "3.0"' not in src, (
        "init_cmd.py still hardcodes schema_version='3.0' — should use SCHEMA_VERSION constant"
    )
    # Must import SCHEMA_VERSION
    assert "SCHEMA_VERSION" in src, (
        "init_cmd.py must reference SCHEMA_VERSION from model.components"
    )
    assert SCHEMA_VERSION  # ensure constant is importable


def test_gallery_uses_schema_version_constant():
    import yaml

    from faultray.model.components import SCHEMA_VERSION
    from faultray.templates.gallery import TemplateGallery

    gallery = TemplateGallery()
    names = gallery.list_templates()
    assert names, "TemplateGallery returned empty list — nothing to verify"

    template_id = names[0].id
    yaml_str = gallery.to_yaml(template_id)
    yaml_dict = yaml.safe_load(yaml_str)
    assert yaml_dict["schema_version"] == SCHEMA_VERSION, (
        f"gallery emitted {yaml_dict['schema_version']!r}, expected "
        f"SCHEMA_VERSION ({SCHEMA_VERSION!r})"
    )
