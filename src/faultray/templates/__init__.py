"""Scenario Templates Library.

Pre-built YAML templates for common infrastructure architectures.
Each template is a valid YAML loadable by :func:`faultray.model.loader.load_yaml`.
"""

from __future__ import annotations

from pathlib import Path


TEMPLATES: dict[str, str] = {
    "web-app": "web_app_basic.yaml",
    "microservices": "microservices.yaml",
    "data-pipeline": "data_pipeline.yaml",
    "ecommerce": "ecommerce.yaml",
    "fintech": "fintech.yaml",
}


def get_template_path(name: str) -> Path:
    """Return the absolute path to a named template YAML file.

    Args:
        name: Template short name (e.g. ``"web-app"``).

    Returns:
        :class:`pathlib.Path` to the YAML file.

    Raises:
        KeyError: If the template name is not recognised.
    """
    if name not in TEMPLATES:
        raise KeyError(
            f"Unknown template '{name}'. "
            f"Available templates: {list(TEMPLATES.keys())}"
        )
    template_dir = Path(__file__).parent
    return template_dir / TEMPLATES[name]


def list_templates() -> list[dict]:
    """Return metadata about all available templates.

    Each entry is a dict with keys ``name``, ``file``, and ``path``.
    """
    template_dir = Path(__file__).parent
    result: list[dict] = []
    for name, filename in TEMPLATES.items():
        result.append({
            "name": name,
            "file": filename,
            "path": str(template_dir / filename),
        })
    return result
