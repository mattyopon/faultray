# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Requirements Parser: テキスト/Markdown要件からRequirementsSpecを生成する。

外部AIサービスに依存しない。正規表現 + ルールベースで実装。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ComponentSpec:
    """Individual component requirement extracted from requirements text."""

    role: str          # "frontend", "api", "database", "cache", "queue", "cdn"
    technology: str    # "React", "Node.js", "PostgreSQL", etc.
    scaling: str       # "fixed", "auto"
    redundancy: bool   # HA required


@dataclass
class RequirementsSpec:
    """Structured requirements parsed from free-form text."""

    app_name: str
    app_type: str                       # web_app/api/microservices/data_pipeline
    components: list[ComponentSpec] = field(default_factory=list)
    availability_target: float = 99.9   # percentage
    expected_traffic: str = "medium"    # "1M PV/month", "100k RPM", etc.
    traffic_scale: str = "medium"       # low/medium/high/very_high
    region: str = "ap-northeast-1"
    budget_range: str = "medium"        # low/medium/high
    security_requirements: list[str] = field(default_factory=list)
    compliance: list[str] = field(default_factory=list)
    multi_az: bool = False
    multi_region: bool = False


# ---------------------------------------------------------------------------
# Keyword tables (rule-based, no external API)
# ---------------------------------------------------------------------------

# Traffic scale detection: pattern → (scale, label)
_TRAFFIC_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"(\d+(?:\.\d+)?)\s*[Mm]?\s*(?:pv|page\s*view)", re.I), "volume", ""),
    (re.compile(r"(\d+(?:\.\d+)?)\s*[Kk]\s*rpm", re.I), "krpm", ""),
    (re.compile(r"(\d+(?:\.\d+)?)\s*[Mm]\s*rpm", re.I), "mrpm", ""),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:万|万[人ユーザー])", re.I), "jp_man", ""),
]

_TECH_ROLE_MAP: dict[str, str] = {
    # Frontend
    "react": "frontend",
    "vue": "frontend",
    "angular": "frontend",
    "next.js": "frontend",
    "nextjs": "frontend",
    "nuxt": "frontend",
    "svelte": "frontend",
    "static site": "frontend",
    "静的サイト": "frontend",
    # API / App server
    "node.js": "api",
    "nodejs": "api",
    "express": "api",
    "fastapi": "api",
    "django": "api",
    "rails": "api",
    "spring": "api",
    "laravel": "api",
    "flask": "api",
    "go": "api",
    "golang": "api",
    "rust": "api",
    "grpc": "api",
    "graphql": "api",
    # Database
    "postgresql": "database",
    "postgres": "database",
    "mysql": "database",
    "aurora": "database",
    "rds": "database",
    "dynamodb": "database",
    "mongodb": "database",
    "sqlite": "database",
    "oracle": "database",
    "sql server": "database",
    "cosmos db": "database",
    # Cache
    "redis": "cache",
    "memcached": "cache",
    "elasticache": "cache",
    # Queue / Messaging
    "sqs": "queue",
    "rabbitmq": "queue",
    "kafka": "queue",
    "sns": "queue",
    "pubsub": "queue",
    "kinesis": "queue",
    # Search
    "elasticsearch": "search",
    "opensearch": "search",
    "solr": "search",
}

_APP_TYPE_KEYWORDS: dict[str, list[str]] = {
    "microservices": [
        "microservice", "マイクロサービス", "service mesh", "kubernetes", "k8s",
        "container orchestration",
    ],
    "data_pipeline": [
        "data pipeline", "etl", "batch", "streaming", "spark", "flink",
        "kinesis", "kafka pipeline", "データパイプライン", "バッチ",
    ],
    "api": [
        "rest api", "graphql api", "api gateway", "backend api", "api server",
        "バックエンドapi",
    ],
    "web_app": [
        "web app", "webapp", "website", "webサービス", "3層", "3-tier",
        "frontend", "react", "vue", "angular",
    ],
}

_COMPLIANCE_KEYWORDS: dict[str, list[str]] = {
    "DORA": ["dora", "deployment frequency", "change failure"],
    "SOC2": ["soc2", "soc 2", "security compliance"],
    "PCI-DSS": ["pci", "pci-dss", "payment card"],
    "HIPAA": ["hipaa", "health data", "医療"],
    "GDPR": ["gdpr", "個人情報保護", "privacy"],
    "ISO27001": ["iso27001", "iso 27001"],
}

_SECURITY_KEYWORDS: list[str] = [
    "waf", "https必須", "https required", "ssl", "tls",
    "rate limiting", "レートリミット", "認証", "authentication",
    "mfa", "multi-factor", "network isolation", "vpc", "private subnet",
]

_REGION_MAP: dict[str, str] = {
    "tokyo": "ap-northeast-1",
    "東京": "ap-northeast-1",
    "japan": "ap-northeast-1",
    "日本": "ap-northeast-1",
    "osaka": "ap-northeast-3",
    "大阪": "ap-northeast-3",
    "singapore": "ap-southeast-1",
    "us-east": "us-east-1",
    "virginia": "us-east-1",
    "us-west": "us-west-2",
    "oregon": "us-west-2",
    "europe": "eu-west-1",
    "ireland": "eu-west-1",
    "frankfurt": "eu-central-1",
}


# ---------------------------------------------------------------------------
# RequirementsParser
# ---------------------------------------------------------------------------


class RequirementsParser:
    """Parse free-form requirements text into RequirementsSpec.

    No external API dependency. Pure rule-based extraction.
    """

    def parse_text(self, text: str) -> RequirementsSpec:
        """Parse requirements from a plain text / Markdown string."""
        lower = text.lower()

        app_name = self._extract_app_name(text)
        app_type = self._detect_app_type(lower)
        availability = self._extract_availability(lower)
        traffic, traffic_scale = self._extract_traffic(lower)
        region = self._extract_region(lower)
        budget = self._extract_budget(lower)
        security = self._extract_security(lower)
        compliance = self._extract_compliance(lower)
        components = self._extract_components(lower, app_type, availability)

        multi_az = availability >= 99.9
        multi_region = availability >= 99.99

        return RequirementsSpec(
            app_name=app_name,
            app_type=app_type,
            components=components,
            availability_target=availability,
            expected_traffic=traffic,
            traffic_scale=traffic_scale,
            region=region,
            budget_range=budget,
            security_requirements=security,
            compliance=compliance,
            multi_az=multi_az,
            multi_region=multi_region,
        )

    def parse_file(self, path: Path) -> RequirementsSpec:
        """Parse requirements from a file (Markdown or plain text)."""
        text = path.read_text(encoding="utf-8")
        return self.parse_text(text)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_app_name(self, text: str) -> str:
        """Extract app name from first heading or first line."""
        # Markdown heading: # App Name
        m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if m:
            return m.group(1).strip()
        # First non-empty line
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                # Truncate to first sentence-ish
                candidate = re.split(r"[。.\n]", stripped)[0][:40]
                if candidate:
                    return candidate
        return "MyApp"

    def _detect_app_type(self, lower: str) -> str:
        """Detect application type from keywords."""
        for app_type, keywords in _APP_TYPE_KEYWORDS.items():
            for kw in keywords:
                if kw in lower:
                    return app_type
        return "web_app"  # default

    def _extract_availability(self, lower: str) -> float:
        """Extract availability target (e.g. '99.9%', '99.99%')."""
        # Match patterns like 99.9%, 99.99%, four nines, five nines
        m = re.search(r"(99\.9{1,3})\s*%", lower)
        if m:
            return float(m.group(1))
        if "five nines" in lower or "99.999" in lower:
            return 99.999
        if "four nines" in lower or "99.99" in lower:
            return 99.99
        if "three nines" in lower or "99.9" in lower:
            return 99.9
        if "two nines" in lower or "99%" in lower:
            return 99.0
        return 99.9  # conservative default

    def _extract_traffic(self, lower: str) -> tuple[str, str]:
        """Extract traffic description and scale label."""
        # PV per month: 1M, 100万, etc.
        m = re.search(r"(\d+(?:\.\d+)?)\s*[Mm]\s*(?:pv|pageview|page view|pvs)", lower)
        if m:
            pv_millions = float(m.group(1))
            label = f"{m.group(1)}M PV/month"
            if pv_millions >= 10:
                return label, "very_high"
            if pv_millions >= 1:
                return label, "high"
            return label, "medium"

        # Japanese: 万PV
        m = re.search(r"(\d+)\s*万\s*(?:pv|ページ|ユーザー)", lower)
        if m:
            pv_man = int(m.group(1))
            label = f"{m.group(1)}万 PV/month"
            if pv_man >= 100:
                return label, "high"
            if pv_man >= 10:
                return label, "medium"
            return label, "low"

        # RPM
        m = re.search(r"(\d+)\s*[Kk]\s*rpm", lower)
        if m:
            krpm = int(m.group(1))
            label = f"{m.group(1)}K RPM"
            if krpm >= 100:
                return label, "very_high"
            if krpm >= 10:
                return label, "high"
            return label, "medium"

        # Keywords
        if any(k in lower for k in ["large scale", "大規模", "enterprise", "エンタープライズ"]):
            return "enterprise scale", "very_high"
        if any(k in lower for k in ["medium", "中規模"]):
            return "medium scale", "medium"
        if any(k in lower for k in ["small", "小規模", "startup", "スタートアップ"]):
            return "small scale", "low"

        return "medium scale", "medium"

    def _extract_region(self, lower: str) -> str:
        """Extract AWS region from region keywords."""
        for keyword, region in _REGION_MAP.items():
            if keyword in lower:
                return region
        # Explicit region code like ap-northeast-1
        m = re.search(r"(ap|us|eu|sa|ca|me|af)-[a-z]+-\d", lower)
        if m:
            return m.group(0)
        return "ap-northeast-1"  # default to Tokyo

    def _extract_budget(self, lower: str) -> str:
        """Extract budget range keyword."""
        if any(k in lower for k in ["high budget", "enterprise", "エンタープライズ", "大企業"]):
            return "high"
        if any(k in lower for k in ["low budget", "startup", "スタートアップ", "個人"]):
            return "low"
        return "medium"

    def _extract_security(self, lower: str) -> list[str]:
        """Extract security requirements."""
        found: list[str] = []
        for kw in _SECURITY_KEYWORDS:
            if kw in lower:
                found.append(kw)
        # Always add HTTPS for web apps
        if "https" not in " ".join(found) and any(
            k in lower for k in ["web", "http", "api", "frontend"]
        ):
            found.append("HTTPS必須")
        return found

    def _extract_compliance(self, lower: str) -> list[str]:
        """Extract compliance framework requirements."""
        found: list[str] = []
        for framework, keywords in _COMPLIANCE_KEYWORDS.items():
            for kw in keywords:
                if kw in lower:
                    found.append(framework)
                    break
        return found

    def _extract_components(
        self, lower: str, app_type: str, availability: float
    ) -> list[ComponentSpec]:
        """Extract component specs from requirements text."""
        found_roles: dict[str, ComponentSpec] = {}
        redundancy = availability >= 99.9

        # Match known technology names
        for tech, role in _TECH_ROLE_MAP.items():
            if tech in lower:
                if role not in found_roles:
                    scaling = "auto" if any(
                        k in lower for k in ["autoscale", "auto-scale", "自動スケール", "オートスケール"]
                    ) else "fixed"
                    found_roles[role] = ComponentSpec(
                        role=role,
                        technology=_CANONICAL_TECH.get(tech, tech.title()),
                        scaling=scaling,
                        redundancy=redundancy,
                    )

        # Pattern: "3層", "three tier", "3-tier" → infer web/api/db
        if re.search(r"3\s*層|three.tier|3.tier", lower):
            if "frontend" not in found_roles:
                found_roles["frontend"] = ComponentSpec(
                    role="frontend", technology="React", scaling="fixed", redundancy=redundancy
                )
            if "api" not in found_roles:
                found_roles["api"] = ComponentSpec(
                    role="api", technology="Node.js", scaling="auto", redundancy=redundancy
                )
            if "database" not in found_roles:
                found_roles["database"] = ComponentSpec(
                    role="database", technology="PostgreSQL", scaling="fixed", redundancy=redundancy
                )

        # Apply defaults per app_type if nothing detected
        if not found_roles:
            found_roles = _default_components(app_type, redundancy)

        # Add CDN for web apps with high traffic
        if app_type == "web_app" and "cdn" not in found_roles:
            if "cdn" in lower or "cloudfront" in lower or any(
                k in lower for k in ["高トラフィック", "high traffic"]
            ):
                found_roles["cdn"] = ComponentSpec(
                    role="cdn", technology="CloudFront", scaling="auto", redundancy=True
                )

        # Add cache if not present and traffic is high
        if "cache" not in found_roles and any(
            k in lower for k in ["cache", "キャッシュ", "高速", "パフォーマンス"]
        ):
            found_roles["cache"] = ComponentSpec(
                role="cache", technology="Redis", scaling="fixed", redundancy=redundancy
            )

        return list(found_roles.values())


# Canonical display names for technologies
_CANONICAL_TECH: dict[str, str] = {
    "react": "React",
    "vue": "Vue.js",
    "angular": "Angular",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "nuxt": "Nuxt.js",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "express": "Express",
    "fastapi": "FastAPI",
    "django": "Django",
    "rails": "Rails",
    "spring": "Spring Boot",
    "flask": "Flask",
    "golang": "Go",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "aurora": "Aurora",
    "rds": "RDS",
    "dynamodb": "DynamoDB",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "memcached": "Memcached",
    "elasticache": "ElastiCache",
    "sqs": "SQS",
    "kafka": "Kafka",
    "rabbitmq": "RabbitMQ",
    "elasticsearch": "Elasticsearch",
    "opensearch": "OpenSearch",
}


def _default_components(app_type: str, redundancy: bool) -> dict[str, ComponentSpec]:
    """Return default component set for a given app type."""
    defaults: dict[str, dict[str, ComponentSpec]] = {
        "web_app": {
            "frontend": ComponentSpec("frontend", "React", "fixed", redundancy),
            "api": ComponentSpec("api", "Node.js", "auto", redundancy),
            "database": ComponentSpec("database", "PostgreSQL", "fixed", redundancy),
        },
        "api": {
            "api": ComponentSpec("api", "Node.js", "auto", redundancy),
            "database": ComponentSpec("database", "PostgreSQL", "fixed", redundancy),
            "cache": ComponentSpec("cache", "Redis", "fixed", redundancy),
        },
        "microservices": {
            "api": ComponentSpec("api", "Node.js", "auto", redundancy),
            "database": ComponentSpec("database", "PostgreSQL", "fixed", redundancy),
            "queue": ComponentSpec("queue", "SQS", "auto", True),
            "cache": ComponentSpec("cache", "Redis", "fixed", redundancy),
        },
        "data_pipeline": {
            "queue": ComponentSpec("queue", "Kafka", "auto", redundancy),
            "database": ComponentSpec("database", "PostgreSQL", "fixed", redundancy),
            "storage": ComponentSpec("storage", "S3", "auto", True),
        },
    }
    return defaults.get(app_type, defaults["web_app"])
