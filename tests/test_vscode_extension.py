"""Tests to verify VS Code extension scaffold and MkDocs documentation files exist."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Project root (two levels up from tests/)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# VS Code Extension scaffold tests
# ---------------------------------------------------------------------------

class TestVSCodeExtension:
    """Verify that the VS Code extension scaffold files are in place."""

    def test_vscode_package_json_exists(self):
        assert (ROOT / "vscode-extension" / "package.json").exists()

    def test_vscode_extension_ts_exists(self):
        assert (ROOT / "vscode-extension" / "src" / "extension.ts").exists()

    def test_vscode_tsconfig_exists(self):
        assert (ROOT / "vscode-extension" / "tsconfig.json").exists()

    def test_vscode_readme_exists(self):
        assert (ROOT / "vscode-extension" / "README.md").exists()

    def test_package_json_valid(self):
        pkg = ROOT / "vscode-extension" / "package.json"
        data = json.loads(pkg.read_text())
        assert data["name"] == "faultzero-vscode"
        assert "main" in data
        assert "contributes" in data
        assert len(data["contributes"]["commands"]) >= 3

    def test_extension_ts_has_activate(self):
        src = (ROOT / "vscode-extension" / "src" / "extension.ts").read_text()
        assert "export function activate" in src
        assert "export function deactivate" in src

    def test_tsconfig_valid(self):
        tsconfig = ROOT / "vscode-extension" / "tsconfig.json"
        data = json.loads(tsconfig.read_text())
        assert data["compilerOptions"]["module"] == "commonjs"
        assert data["compilerOptions"]["outDir"] == "out"


# ---------------------------------------------------------------------------
# MkDocs documentation tests
# ---------------------------------------------------------------------------

class TestMkDocs:
    """Verify that MkDocs documentation structure is in place."""

    def test_mkdocs_yml_exists(self):
        assert (ROOT / "mkdocs.yml").exists()

    def test_docs_index_exists(self):
        assert (ROOT / "docs" / "index.md").exists()

    # Getting Started
    def test_installation_exists(self):
        assert (ROOT / "docs" / "getting-started" / "installation.md").exists()

    def test_quickstart_exists(self):
        assert (ROOT / "docs" / "getting-started" / "quickstart.md").exists()

    def test_first_simulation_exists(self):
        assert (ROOT / "docs" / "getting-started" / "first-simulation.md").exists()

    # Concepts
    def test_how_it_works_exists(self):
        assert (ROOT / "docs" / "concepts" / "how-it-works.md").exists()

    def test_five_layer_model_exists(self):
        assert (ROOT / "docs" / "concepts" / "five-layer-model.md").exists()

    def test_risk_scoring_exists(self):
        assert (ROOT / "docs" / "concepts" / "risk-scoring.md").exists()

    # CLI Reference
    def test_cli_commands_exists(self):
        assert (ROOT / "docs" / "cli" / "commands.md").exists()

    # API Reference
    def test_rest_api_exists(self):
        assert (ROOT / "docs" / "api" / "rest.md").exists()

    def test_graphql_exists(self):
        assert (ROOT / "docs" / "api" / "graphql.md").exists()

    def test_python_sdk_exists(self):
        assert (ROOT / "docs" / "api" / "python-sdk.md").exists()

    # Integrations
    def test_aws_integration_exists(self):
        assert (ROOT / "docs" / "integrations" / "aws.md").exists()

    def test_gcp_integration_exists(self):
        assert (ROOT / "docs" / "integrations" / "gcp.md").exists()

    def test_azure_integration_exists(self):
        assert (ROOT / "docs" / "integrations" / "azure.md").exists()

    def test_kubernetes_integration_exists(self):
        assert (ROOT / "docs" / "integrations" / "kubernetes.md").exists()

    def test_terraform_integration_exists(self):
        assert (ROOT / "docs" / "integrations" / "terraform.md").exists()

    def test_cicd_integration_exists(self):
        assert (ROOT / "docs" / "integrations" / "cicd.md").exists()

    def test_slack_integration_exists(self):
        assert (ROOT / "docs" / "integrations" / "slack.md").exists()

    # Enterprise
    def test_compliance_exists(self):
        assert (ROOT / "docs" / "enterprise" / "compliance.md").exists()

    def test_insurance_exists(self):
        assert (ROOT / "docs" / "enterprise" / "insurance.md").exists()

    def test_rbac_exists(self):
        assert (ROOT / "docs" / "enterprise" / "rbac.md").exists()

    # Content validation
    def test_docs_have_content(self):
        """All doc files should have meaningful content (not just a title)."""
        docs_dir = ROOT / "docs"
        for md_file in docs_dir.rglob("*.md"):
            content = md_file.read_text()
            # Each file should have at least a heading and some content
            assert len(content) > 100, f"{md_file} has too little content ({len(content)} chars)"
            assert content.startswith("#"), f"{md_file} does not start with a heading"

    def test_mkdocs_nav_matches_files(self):
        """All files referenced in mkdocs.yml nav should exist."""
        import yaml

        mkdocs_path = ROOT / "mkdocs.yml"
        with open(mkdocs_path) as f:
            config = yaml.safe_load(f)

        def extract_paths(nav_items):
            paths = []
            for item in nav_items:
                if isinstance(item, str):
                    paths.append(item)
                elif isinstance(item, dict):
                    for value in item.values():
                        if isinstance(value, str):
                            paths.append(value)
                        elif isinstance(value, list):
                            paths.extend(extract_paths(value))
            return paths

        nav_paths = extract_paths(config["nav"])
        for rel_path in nav_paths:
            full_path = ROOT / "docs" / rel_path
            assert full_path.exists(), f"mkdocs.yml references {rel_path} but file does not exist"
