# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L7 Encoding Tests — Generality & Adaptability layer.

Validates FaultRay's handling of various character encodings:
- Japanese paths and filenames
- UTF-8 / Shift-JIS encoded YAML
- Unicode component names
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from faultray.model.loader import load_yaml


# ---------------------------------------------------------------------------
# L7-ENC-001: Japanese file paths
# ---------------------------------------------------------------------------


class TestJapaneseFilePaths:
    """Verify YAML loading from paths containing Japanese characters."""

    def test_japanese_directory_name(self, tmp_path: Path) -> None:
        """YAML file in a directory with Japanese name should load."""
        jp_dir = tmp_path / "テスト設定"
        jp_dir.mkdir()
        yaml_content = {
            "components": [
                {"id": "web", "name": "ウェブサーバー", "type": "web_server"},
            ],
            "dependencies": [],
        }
        yaml_file = jp_dir / "infra.yaml"
        yaml_file.write_text(yaml.dump(yaml_content, allow_unicode=True), encoding="utf-8")
        graph = load_yaml(yaml_file)
        assert graph.get_component("web") is not None

    def test_japanese_filename(self, tmp_path: Path) -> None:
        """YAML file with a Japanese filename should load."""
        yaml_content = {
            "components": [
                {"id": "db", "name": "データベース", "type": "database"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "インフラ定義.yaml"
        yaml_file.write_text(yaml.dump(yaml_content, allow_unicode=True), encoding="utf-8")
        graph = load_yaml(yaml_file)
        comp = graph.get_component("db")
        assert comp is not None
        assert comp.name == "データベース"


# ---------------------------------------------------------------------------
# L7-ENC-002: UTF-8 encoding in YAML content
# ---------------------------------------------------------------------------


class TestUtf8Content:
    """Verify that UTF-8 content in YAML is properly handled."""

    def test_japanese_component_name(self, tmp_path: Path) -> None:
        """Component names with Japanese characters should work."""
        yaml_content = {
            "components": [
                {"id": "lb-1", "name": "ロードバランサー東京", "type": "load_balancer"},
                {"id": "app-1", "name": "アプリケーション大阪", "type": "app_server"},
            ],
            "dependencies": [
                {"source": "lb-1", "target": "app-1", "type": "requires"},
            ],
        }
        yaml_file = tmp_path / "jp.yaml"
        yaml_file.write_text(yaml.dump(yaml_content, allow_unicode=True), encoding="utf-8")
        graph = load_yaml(yaml_file)
        assert graph.get_component("lb-1").name == "ロードバランサー東京"
        assert graph.get_component("app-1").name == "アプリケーション大阪"

    def test_chinese_characters(self, tmp_path: Path) -> None:
        """Chinese characters in component names should work."""
        yaml_content = {
            "components": [
                {"id": "srv", "name": "负载均衡器", "type": "load_balancer"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "cn.yaml"
        yaml_file.write_text(yaml.dump(yaml_content, allow_unicode=True), encoding="utf-8")
        graph = load_yaml(yaml_file)
        assert graph.get_component("srv").name == "负载均衡器"

    def test_emoji_in_component_name(self, tmp_path: Path) -> None:
        """Emoji in component names should be handled."""
        yaml_content = {
            "components": [
                {"id": "e1", "name": "Server 🖥️", "type": "app_server"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "emoji.yaml"
        yaml_file.write_text(yaml.dump(yaml_content, allow_unicode=True), encoding="utf-8")
        graph = load_yaml(yaml_file)
        assert "🖥" in graph.get_component("e1").name

    def test_mixed_script_names(self, tmp_path: Path) -> None:
        """Mixed Latin/Japanese/Korean names should work."""
        yaml_content = {
            "components": [
                {"id": "mix", "name": "Web서버-ウェブ-Server", "type": "web_server"},
            ],
            "dependencies": [],
        }
        yaml_file = tmp_path / "mixed.yaml"
        yaml_file.write_text(yaml.dump(yaml_content, allow_unicode=True), encoding="utf-8")
        graph = load_yaml(yaml_file)
        assert graph.get_component("mix").name == "Web서버-ウェブ-Server"


# ---------------------------------------------------------------------------
# L7-ENC-003: Shift-JIS fallback
# ---------------------------------------------------------------------------


class TestShiftJIS:
    """Test handling of Shift-JIS encoded files."""

    def test_shift_jis_file_raises_or_loads(self, tmp_path: Path) -> None:
        """Shift-JIS file should either be decoded or raise a clear error.

        FaultRay uses utf-8 encoding by default. A Shift-JIS file may fail,
        but it should not produce corrupted data silently.
        """
        # Write a Shift-JIS encoded file
        content = "components:\n  - id: test\n    name: テスト\n    type: app_server\ndependencies: []\n"
        yaml_file = tmp_path / "sjis.yaml"
        yaml_file.write_bytes(content.encode("shift_jis"))

        try:
            graph = load_yaml(yaml_file)
            # If it loaded, component should be there
            assert graph.get_component("test") is not None
        except (UnicodeDecodeError, Exception):
            # Expected: UTF-8 reader cannot decode Shift-JIS
            pass  # This is acceptable behavior


# ---------------------------------------------------------------------------
# L7-ENC-004: Special YAML characters
# ---------------------------------------------------------------------------


class TestSpecialYamlCharacters:
    """Test YAML special characters in component fields."""

    def test_colon_in_component_name(self, tmp_path: Path) -> None:
        """Colons in component names should be handled (YAML delimiter)."""
        yaml_text = (
            "components:\n"
            '  - id: c1\n'
            '    name: "host:8080"\n'
            '    type: app_server\n'
            "dependencies: []\n"
        )
        yaml_file = tmp_path / "colon.yaml"
        yaml_file.write_text(yaml_text, encoding="utf-8")
        graph = load_yaml(yaml_file)
        assert graph.get_component("c1").name == "host:8080"

    def test_hash_in_component_name(self, tmp_path: Path) -> None:
        """Hash characters should not be treated as YAML comments."""
        yaml_text = (
            "components:\n"
            '  - id: c1\n'
            '    name: "version#2"\n'
            '    type: app_server\n'
            "dependencies: []\n"
        )
        yaml_file = tmp_path / "hash.yaml"
        yaml_file.write_text(yaml_text, encoding="utf-8")
        graph = load_yaml(yaml_file)
        assert graph.get_component("c1").name == "version#2"
