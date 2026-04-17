# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Software package dependency models for supply chain resilience."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PackageSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class PackageVulnerability(BaseModel):
    """A known vulnerability in a package."""

    cve_id: str
    severity: PackageSeverity = PackageSeverity.MEDIUM
    description: str = ""
    fixed_version: str | None = None
    exploitability_score: float = 5.0  # CVSS exploitability (0-10)


class PackageNode(BaseModel):
    """A software package in the dependency tree."""

    name: str
    version: str = "0.0.0"
    ecosystem: str = "npm"  # npm, pypi, maven, go, cargo, nuget
    is_direct: bool = True  # Direct dependency or transitive
    depth: int = 0  # Depth in dependency tree (0 = direct)
    vulnerabilities: list[PackageVulnerability] = Field(default_factory=list)
    installed_in: list[str] = Field(default_factory=list)  # Component IDs that use this package
    license: str = ""


class SBOMConfig(BaseModel):
    """SBOM configuration for a component."""

    packages: list[PackageNode] = Field(default_factory=list)
    manifest_file: str = ""  # e.g., "package.json", "requirements.txt"
    last_audit_date: str = ""
