"""Natural Language to Infrastructure Converter.

Converts plain-text infrastructure descriptions into FaultRay YAML definitions.
Uses pattern matching and NLP heuristics to extract components, relationships,
and configurations from natural language.

Examples:
  "I have 3 web servers behind an ALB connected to Aurora with 2 read replicas"
  -> Generates complete YAML with ALB, 3 web servers, Aurora primary + 2 replicas

  "ALBの後ろにEC2が3台、Auroraに接続、Redis キャッシュあり"
  -> Same, with Japanese input support

This module works WITHOUT requiring an external LLM API. It uses rule-based NLP
with regex patterns and keyword matching, making it:
- Free to use (no API costs)
- Deterministic (same input = same output)
- Works offline
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
)
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Data classes for parsed results
# ---------------------------------------------------------------------------


@dataclass
class InfraToken:
    """A single token extracted from natural language input."""

    text: str
    token_type: str  # "component", "count", "relationship", "property", "unknown"
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedComponent:
    """A component extracted from natural language."""

    name: str  # auto-generated slug
    component_type: ComponentType
    replicas: int = 0  # 0 means "use smart default"
    properties: dict = field(default_factory=dict)
    # Original text snippet that matched
    source_text: str = ""
    # Position in original text (for ordering and proximity matching)
    position: int = -1


@dataclass
class ParsedRelationship:
    """A relationship between two parsed components."""

    source: str  # component name/slug
    target: str  # component name/slug
    relationship_type: str = "requires"  # "requires", "optional", "async"


@dataclass
class ParsedInfrastructure:
    """Complete parsed infrastructure from natural language."""

    components: list[ParsedComponent] = field(default_factory=list)
    relationships: list[ParsedRelationship] = field(default_factory=list)
    raw_text: str = ""


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# Component detection patterns (English + Japanese)
# Order matters: more specific patterns (multi-word) first.
#
# IMPORTANT: Python's \b treats Unicode letters (e.g., Japanese の) as word
# characters (\w).  This means \bALB\b fails to match "ALBの" because B→の
# is w→w, not a boundary.  We use _WB (ASCII-only word boundary) for English
# patterns that may appear adjacent to CJK text.
_WB = r'(?<![a-zA-Z0-9_])(?=[a-zA-Z0-9_])'   # word-start (ASCII)
_WBE = r'(?<=[a-zA-Z0-9_])(?![a-zA-Z0-9_])'   # word-end (ASCII)

def _wb(word: str) -> str:
    """Wrap an English word/acronym with ASCII-safe word boundaries."""
    return _WB + word + _WBE

COMPONENT_PATTERNS: list[tuple[str, ComponentType, str]] = [
    # API Gateway (before generic gateway)
    (_wb(r'API\s*Gateway'), ComponentType.LOAD_BALANCER, "api-gateway"),
    (r'ゲートウェイ', ComponentType.LOAD_BALANCER, "api-gateway"),
    # Load Balancers (multi-word patterns first)
    (_wb(r'load\s*balancers?'), ComponentType.LOAD_BALANCER, "load-balancer"),
    (r'ロードバランサー?', ComponentType.LOAD_BALANCER, "load-balancer"),
    (_wb('ALB'), ComponentType.LOAD_BALANCER, "alb"),
    (_wb('NLB'), ComponentType.LOAD_BALANCER, "nlb"),
    (_wb('ELB'), ComponentType.LOAD_BALANCER, "elb"),
    # CDN (maps to load_balancer in ComponentType)
    (_wb('CloudFront'), ComponentType.LOAD_BALANCER, "cloudfront-cdn"),
    (_wb('CDN'), ComponentType.LOAD_BALANCER, "cdn"),
    (_wb('Fastly'), ComponentType.LOAD_BALANCER, "fastly-cdn"),
    (_wb('Cloudflare'), ComponentType.LOAD_BALANCER, "cloudflare-cdn"),
    # DNS
    (_wb(r'Route\s*53'), ComponentType.DNS, "route53"),
    (_wb('DNS'), ComponentType.DNS, "dns"),
    # Compute (multi-word patterns first)
    (_wb(r'web\s*servers?'), ComponentType.WEB_SERVER, "web-server"),
    (_wb(r'app\s*servers?'), ComponentType.APP_SERVER, "app-server"),
    (_wb('EC2'), ComponentType.APP_SERVER, "ec2"),
    (r'サーバー?', ComponentType.APP_SERVER, "server"),
    (r'インスタンス', ComponentType.APP_SERVER, "instance"),
    # Kubernetes / Functions (map to app_server)
    (_wb('EKS'), ComponentType.APP_SERVER, "eks-cluster"),
    (_wb('GKE'), ComponentType.APP_SERVER, "gke-cluster"),
    (_wb('AKS'), ComponentType.APP_SERVER, "aks-cluster"),
    (_wb(r'(?:Kubernetes|k8s)'), ComponentType.APP_SERVER, "k8s-cluster"),
    (r'クラスター?', ComponentType.APP_SERVER, "cluster"),
    (_wb('Lambda'), ComponentType.APP_SERVER, "lambda"),
    (_wb('serverless'), ComponentType.APP_SERVER, "serverless-function"),
    (r'サーバーレス', ComponentType.APP_SERVER, "serverless-function"),
    # Database
    (_wb('Aurora'), ComponentType.DATABASE, "aurora"),
    (_wb('RDS'), ComponentType.DATABASE, "rds"),
    (_wb('PostgreSQL'), ComponentType.DATABASE, "postgresql"),
    (_wb('MySQL'), ComponentType.DATABASE, "mysql"),
    (_wb('MongoDB'), ComponentType.DATABASE, "mongodb"),
    (_wb('DynamoDB'), ComponentType.DATABASE, "dynamodb"),
    (_wb('database'), ComponentType.DATABASE, "database"),
    (r'データベース', ComponentType.DATABASE, "database"),
    # Cache
    (_wb('Redis'), ComponentType.CACHE, "redis"),
    (_wb('ElastiCache'), ComponentType.CACHE, "elasticache"),
    (_wb('Memcached'), ComponentType.CACHE, "memcached"),
    (r'キャッシュ', ComponentType.CACHE, "cache"),
    (_wb('cache'), ComponentType.CACHE, "cache"),
    # Queue
    (_wb('SQS'), ComponentType.QUEUE, "sqs"),
    (_wb('RabbitMQ'), ComponentType.QUEUE, "rabbitmq"),
    (_wb('Kafka'), ComponentType.QUEUE, "kafka"),
    (_wb('queue'), ComponentType.QUEUE, "queue"),
    (r'キュー', ComponentType.QUEUE, "queue"),
    (r'メッセージ', ComponentType.QUEUE, "message-queue"),
    # Storage
    (_wb('S3'), ComponentType.STORAGE, "s3"),
    (_wb('bucket'), ComponentType.STORAGE, "s3-bucket"),
    (_wb('storage'), ComponentType.STORAGE, "storage"),
    (r'ストレージ', ComponentType.STORAGE, "storage"),
    (r'オブジェクト', ComponentType.STORAGE, "object-storage"),
    # External
    (_wb('Stripe'), ComponentType.EXTERNAL_API, "stripe-api"),
    (_wb('Twilio'), ComponentType.EXTERNAL_API, "twilio-api"),
    (_wb('SendGrid'), ComponentType.EXTERNAL_API, "sendgrid-api"),
    (_wb('external'), ComponentType.EXTERNAL_API, "external-api"),
    (_wb(r'third.party'), ComponentType.EXTERNAL_API, "third-party-api"),
    (r'外部', ComponentType.EXTERNAL_API, "external-api"),
    (r'サードパーティ', ComponentType.EXTERNAL_API, "third-party-api"),
]

# Patterns that should NOT be matched as standalone components when they
# appear adjacent to a known component (e.g., "EC2 instances" -- "instances"
# is a qualifier, not a separate component).
QUALIFIER_PATTERNS: set[str] = {
    "instances", "instance", "nodes", "node", "servers", "server",
    "replicas", "replica", "primary",
    "cache", "queue", "storage", "database",  # generic type words after a named service
}

# Japanese qualifier patterns (generic type words that follow a named service)
QUALIFIER_PATTERNS_JA: set[str] = {
    "キャッシュ", "キュー", "ストレージ", "データベース",
    "サーバー", "サーバ", "インスタンス",
}

# Count detection patterns
# Use (?<![a-zA-Z0-9]) before digits to prevent matching digits inside
# product names (e.g., "2" in "EC2" or "53" in "Route 53").
COUNT_PATTERNS: list[str] = [
    # "3台", "3個", "3つ" (Japanese counters)
    r'(?<![a-zA-Z0-9])(\d+)\s*(?:台|個|つ)',
    # "3 web servers", "3 nodes", "3 instances", "3 replicas"
    r'(?<![a-zA-Z0-9])(\d+)\s+(?:nodes?|instances?|servers?|replicas?)',
    # "with 2 read replicas"
    r'(?:with|having)\s+(\d+)\s+(?:read\s+)?replicas?',
    # "3x ..."
    r'(?<![a-zA-Z0-9])(\d+)x\s+',
]

# Additional pattern to detect a number immediately before a component name
# (e.g., "3 EC2", "2 web servers") -- used in _apply_counts
COUNT_BEFORE_COMPONENT = re.compile(r'(\d+)\s+')

# Relationship patterns (English + Japanese)
# Each tuple: (pattern, relationship_direction, dep_type)
# direction: "forward" means source->match->target in text flow;
#            "reverse" means target->match->source
RELATIONSHIP_PATTERNS: list[tuple[str, str, str]] = [
    # "behind" = A is behind B means A depends on B (B -> A flow)
    (r'(?:behind|の後ろに?|後ろに)', "reverse", "requires"),
    (r'前に', "forward", "requires"),
    # "connected to"
    (r'(?:connects?\s+to|connected\s+to)', "forward", "requires"),
    # Japanese "に接続"
    (r'に接続', "forward", "requires"),
    # "backed by"
    (r'(?:backed\s+by|backed\s+with)', "forward", "requires"),
    (r'を使', "forward", "requires"),
    # "sends to"
    (r'(?:sends?\s+to|writes?\s+to)', "forward", "async"),
    (r'に送信', "forward", "async"),
    # "reads from"
    (r'(?:reads?\s+from)', "reverse", "optional"),
    (r'から読', "reverse", "optional"),
    # "through"
    (r'(?:through|経由|を通して)', "forward", "requires"),
    # "distributing to"
    (r'(?:distributing\s+to|distribute\s+to)', "forward", "requires"),
    # "with" (weak relationship)
    (r'(?:with\s+(?:a\s+)?(?:read\s+)?replica)', "forward", "requires"),
    # "for" as in "Redis for caching"
    (r'\bfor\b', "forward", "optional"),
]

# Property detection patterns
PROPERTY_PATTERNS: list[tuple[str, str, Any]] = [
    (r'(\d+)\s*(?:vCPU|CPU|コア)', "cpu", None),
    (r'(\d+)\s*(?:GB|GiB)\s*(?:RAM|memory|メモリ)', "memory_gb", None),
    (r'(\d+)\s*(?:GB|TB)\s*(?:storage|disk|SSD|ストレージ)', "storage_gb", None),
    (r'(?:multi[.\- ]?az|マルチAZ|複数AZ)', "multi_az", True),
    (r'(?:auto[.\- ]?scal(?:e|ing)?(?:\s+enabled)?|オートスケール)', "autoscaling", True),
    (r'(?:circuit[.\- ]?breakers?|サーキットブレーカー?)', "circuit_breaker", True),
    (r'(?:failover|フェイルオーバー?)', "failover", True),
    (r'(?:health[.\- ]?checks?|ヘルスチェック)', "health_check", True),
]

# Smart defaults by component type
SMART_DEFAULTS: dict[ComponentType, dict[str, Any]] = {
    ComponentType.LOAD_BALANCER: {
        "replicas": 2,
        "cpu": 2,
        "memory_gb": 4,
        "failover": True,
        "port": 443,
        "max_connections": 10000,
        "max_rps": 50000,
    },
    ComponentType.WEB_SERVER: {
        "replicas": 2,
        "cpu": 4,
        "memory_gb": 8,
        "port": 8080,
        "max_connections": 5000,
    },
    ComponentType.APP_SERVER: {
        "replicas": 2,
        "cpu": 4,
        "memory_gb": 8,
        "port": 8080,
        "max_connections": 5000,
    },
    ComponentType.DATABASE: {
        "replicas": 2,
        "cpu": 8,
        "memory_gb": 32,
        "storage_gb": 100,
        "failover": True,
        "port": 5432,
        "max_connections": 500,
    },
    ComponentType.CACHE: {
        "replicas": 2,
        "cpu": 2,
        "memory_gb": 16,
        "port": 6379,
        "max_connections": 10000,
    },
    ComponentType.QUEUE: {
        "replicas": 2,
        "cpu": 2,
        "memory_gb": 8,
        "port": 9092,
        "max_connections": 5000,
    },
    ComponentType.STORAGE: {
        "replicas": 1,
        "port": 443,
    },
    ComponentType.DNS: {
        "replicas": 2,
        "port": 53,
    },
    ComponentType.EXTERNAL_API: {
        "replicas": 1,
        "port": 443,
    },
    ComponentType.CUSTOM: {
        "replicas": 1,
        "port": 443,
    },
}

# Auto-inferred dependency order (source_type -> target_type)
# When no explicit relationship is given but both types exist
AUTO_RELATIONSHIP_ORDER: list[tuple[ComponentType, ComponentType, str]] = [
    # DNS -> CDN / LB
    (ComponentType.DNS, ComponentType.LOAD_BALANCER, "requires"),
    # LB -> Server
    (ComponentType.LOAD_BALANCER, ComponentType.WEB_SERVER, "requires"),
    (ComponentType.LOAD_BALANCER, ComponentType.APP_SERVER, "requires"),
    # Server -> Database
    (ComponentType.WEB_SERVER, ComponentType.DATABASE, "requires"),
    (ComponentType.APP_SERVER, ComponentType.DATABASE, "requires"),
    # Server -> Cache
    (ComponentType.WEB_SERVER, ComponentType.CACHE, "optional"),
    (ComponentType.APP_SERVER, ComponentType.CACHE, "optional"),
    # Server -> Queue
    (ComponentType.WEB_SERVER, ComponentType.QUEUE, "async"),
    (ComponentType.APP_SERVER, ComponentType.QUEUE, "async"),
    # Server -> Storage
    (ComponentType.WEB_SERVER, ComponentType.STORAGE, "optional"),
    (ComponentType.APP_SERVER, ComponentType.STORAGE, "optional"),
    # Server -> External API
    (ComponentType.WEB_SERVER, ComponentType.EXTERNAL_API, "optional"),
    (ComponentType.APP_SERVER, ComponentType.EXTERNAL_API, "optional"),
]

# Protocol mapping by component type pair
PROTOCOL_MAP: dict[tuple[ComponentType, ComponentType], str] = {
    (ComponentType.LOAD_BALANCER, ComponentType.WEB_SERVER): "https",
    (ComponentType.LOAD_BALANCER, ComponentType.APP_SERVER): "https",
    (ComponentType.WEB_SERVER, ComponentType.DATABASE): "tcp",
    (ComponentType.APP_SERVER, ComponentType.DATABASE): "tcp",
    (ComponentType.WEB_SERVER, ComponentType.CACHE): "tcp",
    (ComponentType.APP_SERVER, ComponentType.CACHE): "tcp",
    (ComponentType.WEB_SERVER, ComponentType.QUEUE): "tcp",
    (ComponentType.APP_SERVER, ComponentType.QUEUE): "tcp",
    (ComponentType.WEB_SERVER, ComponentType.STORAGE): "https",
    (ComponentType.APP_SERVER, ComponentType.STORAGE): "https",
    (ComponentType.DNS, ComponentType.LOAD_BALANCER): "https",
    (ComponentType.WEB_SERVER, ComponentType.EXTERNAL_API): "https",
    (ComponentType.APP_SERVER, ComponentType.EXTERNAL_API): "https",
    (ComponentType.LOAD_BALANCER, ComponentType.LOAD_BALANCER): "https",
}

# Latency defaults by protocol
LATENCY_DEFAULTS: dict[str, float] = {
    "https": 5.0,
    "tcp": 2.0,
    "grpc": 3.0,
}

# Human-readable names for component types
COMPONENT_TYPE_NAMES: dict[ComponentType, str] = {
    ComponentType.LOAD_BALANCER: "Load Balancer",
    ComponentType.WEB_SERVER: "Web Server",
    ComponentType.APP_SERVER: "App Server",
    ComponentType.DATABASE: "Database",
    ComponentType.CACHE: "Cache",
    ComponentType.QUEUE: "Queue",
    ComponentType.STORAGE: "Storage",
    ComponentType.DNS: "DNS",
    ComponentType.EXTERNAL_API: "External API",
    ComponentType.CUSTOM: "Custom",
}


# ---------------------------------------------------------------------------
# NLInfraParser - Main parser class
# ---------------------------------------------------------------------------


class NLInfraParser:
    """Parse natural language infrastructure descriptions into structured models.

    Supports English and Japanese input. Uses rule-based NLP with regex patterns
    and keyword matching -- no external LLM API required.
    """

    def parse(self, text: str) -> ParsedInfrastructure:
        """Parse natural language text into a ParsedInfrastructure.

        Args:
            text: Natural language description of infrastructure.
                  Can be English, Japanese, or mixed.

        Returns:
            ParsedInfrastructure with extracted components and relationships.

        Raises:
            ValueError: If text is empty or no components could be extracted.
        """
        if not text or not text.strip():
            raise ValueError("Input text is empty")

        text = text.strip()
        result = ParsedInfrastructure(raw_text=text)

        # Step 1: Extract components
        result.components = self._extract_components(text)

        if not result.components:
            raise ValueError(
                f"No infrastructure components found in: {text!r}. "
                "Try mentioning specific services like ALB, EC2, Aurora, Redis, etc."
            )

        # Step 2: Apply count modifiers to nearby components
        self._apply_counts(text, result.components)

        # Step 3: Extract properties and apply to components
        self._apply_properties(text, result.components)

        # Step 4: Apply smart defaults for unset values
        self._apply_smart_defaults(result.components)

        # Step 5: Handle read replicas for databases
        self._handle_replicas(text, result.components)

        # Step 6: Extract explicit relationships
        result.relationships = self._extract_relationships(text, result.components)

        # Step 7: Auto-infer missing relationships
        self._auto_infer_relationships(result)

        # Step 8: Deduplicate component IDs
        self._deduplicate_ids(result.components)

        return result

    def to_yaml(self, parsed: ParsedInfrastructure) -> str:
        """Generate YAML string matching FaultRay format from parsed infrastructure.

        Args:
            parsed: A ParsedInfrastructure from parse().

        Returns:
            YAML string in FaultRay format.
        """
        yaml_data = self._build_yaml_dict(parsed)
        return yaml.dump(
            yaml_data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    def to_graph(self, parsed: ParsedInfrastructure) -> InfraGraph:
        """Generate an InfraGraph directly from parsed infrastructure.

        Args:
            parsed: A ParsedInfrastructure from parse().

        Returns:
            InfraGraph with components and dependencies.
        """
        graph = InfraGraph()

        for pc in parsed.components:
            component = self._parsed_to_component(pc)
            graph.add_component(component)

        for pr in parsed.relationships:
            # Only add if both source and target exist in the graph
            comp_ids = {c.name for c in parsed.components}
            if pr.source in comp_ids and pr.target in comp_ids:
                source_comp = next(c for c in parsed.components if c.name == pr.source)
                target_comp = next(c for c in parsed.components if c.name == pr.target)
                protocol = PROTOCOL_MAP.get(
                    (source_comp.component_type, target_comp.component_type), "tcp"
                )
                latency = LATENCY_DEFAULTS.get(protocol, 5.0)

                dep = Dependency(
                    source_id=pr.source,
                    target_id=pr.target,
                    dependency_type=pr.relationship_type,
                    protocol=protocol,
                    latency_ms=latency,
                    weight=1.0 if pr.relationship_type == "requires" else 0.7,
                )
                graph.add_dependency(dep)

        return graph

    # ------------------------------------------------------------------
    # Internal extraction methods
    # ------------------------------------------------------------------

    def _extract_components(self, text: str) -> list[ParsedComponent]:
        """Extract components from text using pattern matching."""
        components: list[ParsedComponent] = []
        used_positions: list[tuple[int, int]] = []

        for pattern, comp_type, slug in COMPONENT_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                start, end = match.span()
                matched_text = match.group(0)

                # Skip if this is a qualifier word adjacent to an already-matched
                # component of the same or related type (e.g., "instances"
                # in "EC2 instances", "キャッシュ" in "Redisキャッシュ").
                # Only suppress when the nearby component has the SAME
                # component_type (prevents "サーバー" after "ロードバランサー"
                # from being suppressed since LB != APP_SERVER).
                is_en_qualifier = matched_text.lower().rstrip("s") in {
                    q.rstrip("s") for q in QUALIFIER_PATTERNS
                }
                is_ja_qualifier = matched_text in QUALIFIER_PATTERNS_JA

                if is_en_qualifier or is_ja_qualifier:
                    is_qualifier = False
                    for used_start, used_end in used_positions:
                        if used_end <= start and start - used_end <= 15:
                            # Find the component that occupies the nearby span
                            nearby_comp = next(
                                (c for c in components
                                 if c.position >= used_start
                                 and c.position < used_end),
                                None,
                            )
                            if nearby_comp is None:
                                if is_en_qualifier:
                                    is_qualifier = True
                                    break
                            elif nearby_comp.component_type == comp_type:
                                # Same type: definitely a qualifier
                                is_qualifier = True
                                break
                            elif is_en_qualifier:
                                # English qualifiers like "instances", "servers"
                                # always qualify regardless of type
                                is_qualifier = True
                                break
                            # For Japanese qualifiers with different type:
                            # don't break, keep checking other positions
                    if is_qualifier:
                        continue

                # Check for overlap with already matched components
                overlaps = False
                for used_start, used_end in used_positions:
                    if start < used_end and end > used_start:
                        overlaps = True
                        break

                if overlaps:
                    continue

                used_positions.append((start, end))
                components.append(ParsedComponent(
                    name=slug,
                    component_type=comp_type,
                    source_text=matched_text,
                    position=start,
                ))

        # Sort by position in text (preserves natural order)
        components.sort(key=lambda c: c.position)

        return components

    def _apply_counts(self, text: str, components: list[ParsedComponent]) -> None:
        """Apply count modifiers to nearby components.

        Uses two strategies:
        1. Number-before-component detection ("3 EC2", "3 web servers")
        2. Pattern matching for explicit count phrases ("3 servers", "3台")

        For count phrases that appear *after* a component (e.g., "EC2が3台"),
        we prefer the component immediately preceding the count.
        """
        # Strategy 1: detect "N <component>" pattern by looking at what's
        # immediately before each component in the text
        for comp in components:
            if comp.replicas != 0:
                continue

            # Look at text before the component position for a number
            before_text = text[:comp.position].rstrip()
            num_match = re.search(r'(?<![a-zA-Z0-9])(\d+)\s*$', before_text)
            if num_match:
                comp.replicas = int(num_match.group(1))

        # Strategy 2: count pattern matching
        for pattern_str in COUNT_PATTERNS:
            for match in re.finditer(pattern_str, text, re.IGNORECASE):
                count = int(match.group(1))
                match_start = match.start()

                # Find the closest component that PRECEDES this count
                # (e.g., "EC2が3台" -> 3 applies to EC2, not the next component)
                closest_comp = self._find_preceding_component(
                    components, match_start, max_dist=20
                )

                # If no preceding component, try the closest one overall
                if closest_comp is None:
                    closest_comp = self._find_closest_component(
                        components, text, match_start, max_dist=60
                    )

                if closest_comp and closest_comp.replicas == 0:
                    closest_comp.replicas = count

    def _find_closest_component(
        self,
        components: list[ParsedComponent],
        text: str,
        ref_pos: int,
        max_dist: int = 60,
    ) -> ParsedComponent | None:
        """Find the component closest to ref_pos in text."""
        closest_comp = None
        closest_dist = float("inf")

        for comp in components:
            dist = abs(comp.position - ref_pos)
            if dist < closest_dist and dist <= max_dist:
                closest_dist = dist
                closest_comp = comp

        return closest_comp

    def _find_preceding_component(
        self,
        components: list[ParsedComponent],
        ref_pos: int,
        max_dist: int = 20,
    ) -> ParsedComponent | None:
        """Find the closest component that appears BEFORE ref_pos in text.

        This is used for count/property phrases that modify the preceding
        component (e.g., "EC2が3台" -> 3 applies to EC2).
        """
        best = None
        best_dist = float("inf")

        for comp in components:
            if comp.position < ref_pos:
                dist = ref_pos - comp.position
                if dist <= max_dist and dist < best_dist:
                    best_dist = dist
                    best = comp

        return best

    def _apply_properties(self, text: str, components: list[ParsedComponent]) -> None:
        """Extract properties from text and apply to contextually nearest component.

        Properties are assigned to the most recent preceding component if one
        exists within a reasonable distance, otherwise to the globally closest
        component.  This captures natural phrasing like "4 web servers with
        8 vCPU, autoscaling enabled" where all properties belong to web-server.
        """
        for pattern_str, prop_name, static_value in PROPERTY_PATTERNS:
            for match in re.finditer(pattern_str, text, re.IGNORECASE):
                if static_value is not None:
                    value = static_value
                else:
                    value = int(match.group(1))

                match_pos = match.start()

                # Prefer the most recent component that precedes this property,
                # as long as there is no major separator ("." new sentence) in
                # between.  Fall back to globally closest.
                target_comp = self._find_preceding_component(
                    components, match_pos, max_dist=120
                )

                if target_comp is None:
                    target_comp = self._find_closest_component(
                        components, text, match_pos, max_dist=200
                    )

                if target_comp:
                    target_comp.properties[prop_name] = value

    def _apply_smart_defaults(self, components: list[ParsedComponent]) -> None:
        """Apply smart defaults for unset values based on component type."""
        for comp in components:
            defaults = SMART_DEFAULTS.get(comp.component_type, {})

            # Apply replica default if not set
            if comp.replicas == 0:
                comp.replicas = defaults.get("replicas", 1)

            # Apply other defaults for unset properties
            for key, value in defaults.items():
                if key != "replicas" and key not in comp.properties:
                    comp.properties[key] = value

    def _handle_replicas(self, text: str, components: list[ParsedComponent]) -> None:
        """Handle read replica patterns for databases.

        If text mentions "N read replicas" near a database, create an
        additional database component for the replicas.
        """
        replica_patterns = [
            r'(?:with|having)\s+(\d+)\s+read\s+replicas?',
            r'(\d+)\s+read\s+replicas?',
            r'リードレプリカ\s*(\d+)',
            r'(\d+)\s*(?:台|個)?\s*(?:の)?レプリカ',
            r'(?:a|1)\s+read\s+replica',  # "a read replica" = 1
        ]

        new_components: list[ParsedComponent] = []

        for pattern_str in replica_patterns:
            for match in re.finditer(pattern_str, text, re.IGNORECASE):
                # Try to get count from group, default to 1 for "a read replica"
                try:
                    count = int(match.group(1))
                except (IndexError, TypeError):
                    count = 1

                match_pos = match.start()

                # Find the closest database component
                closest_db = None
                closest_dist = float("inf")

                for comp in components:
                    if comp.component_type == ComponentType.DATABASE:
                        dist = abs(comp.position - match_pos)
                        if dist < closest_dist:
                            closest_dist = dist
                            closest_db = comp

                if closest_db:
                    # Rename the original to "primary"
                    if not closest_db.name.endswith("-primary"):
                        closest_db.name = f"{closest_db.name}-primary"
                        closest_db.replicas = 1

                    # Create replica component
                    replica_name = closest_db.name.replace("-primary", "-replica")
                    # Avoid adding duplicates
                    existing_names = {c.name for c in components} | {
                        c.name for c in new_components
                    }
                    if replica_name not in existing_names:
                        replica = ParsedComponent(
                            name=replica_name,
                            component_type=ComponentType.DATABASE,
                            replicas=count,
                            properties=dict(closest_db.properties),
                            source_text=match.group(0),
                            position=match_pos + 1000,  # append to end
                        )
                        new_components.append(replica)

        components.extend(new_components)

    def _extract_relationships(
        self, text: str, components: list[ParsedComponent]
    ) -> list[ParsedRelationship]:
        """Extract explicit relationships from text."""
        relationships: list[ParsedRelationship] = []

        # Build sorted position list for components
        comp_positions: list[tuple[int, ParsedComponent]] = [
            (comp.position, comp) for comp in components
        ]
        comp_positions.sort(key=lambda x: x[0])

        if len(comp_positions) < 2:
            return relationships

        # For each relationship keyword, find surrounding components
        for pattern_str, direction, dep_type in RELATIONSHIP_PATTERNS:
            for match in re.finditer(pattern_str, text, re.IGNORECASE):
                rel_pos = match.start()

                # Find closest component before and after the relationship word
                before = None
                after = None

                for pos, comp in comp_positions:
                    if pos < rel_pos:
                        before = comp
                    elif pos >= rel_pos and after is None:
                        after = comp

                if before and after and before.name != after.name:
                    if direction == "forward":
                        source, target = before, after
                    else:
                        source, target = after, before

                    # Avoid duplicate relationships
                    exists = any(
                        r.source == source.name and r.target == target.name
                        for r in relationships
                    )
                    if not exists:
                        relationships.append(ParsedRelationship(
                            source=source.name,
                            target=target.name,
                            relationship_type=dep_type,
                        ))

        return relationships

    def _auto_infer_relationships(self, parsed: ParsedInfrastructure) -> None:
        """Auto-infer relationships when explicit ones are insufficient."""
        # Only auto-infer if we have few explicit relationships relative
        # to the number of components
        if len(parsed.relationships) >= len(parsed.components) - 1:
            return

        existing_pairs = {
            (r.source, r.target) for r in parsed.relationships
        }

        comp_by_type: dict[ComponentType, list[ParsedComponent]] = {}
        for comp in parsed.components:
            comp_by_type.setdefault(comp.component_type, []).append(comp)

        for source_type, target_type, dep_type in AUTO_RELATIONSHIP_ORDER:
            sources = comp_by_type.get(source_type, [])
            targets = comp_by_type.get(target_type, [])

            for source in sources:
                for target in targets:
                    if source.name == target.name:
                        continue
                    pair = (source.name, target.name)
                    reverse_pair = (target.name, source.name)
                    if pair not in existing_pairs and reverse_pair not in existing_pairs:
                        parsed.relationships.append(ParsedRelationship(
                            source=source.name,
                            target=target.name,
                            relationship_type=dep_type,
                        ))
                        existing_pairs.add(pair)

        # Handle DB primary -> replica relationship
        for comp in parsed.components:
            if (
                comp.component_type == ComponentType.DATABASE
                and comp.name.endswith("-primary")
            ):
                replica_name = comp.name.replace("-primary", "-replica")
                for other in parsed.components:
                    if other.name == replica_name:
                        pair = (comp.name, replica_name)
                        if pair not in existing_pairs:
                            parsed.relationships.append(ParsedRelationship(
                                source=comp.name,
                                target=replica_name,
                                relationship_type="async",
                            ))
                            existing_pairs.add(pair)

    def _deduplicate_ids(self, components: list[ParsedComponent]) -> None:
        """Ensure all component IDs are unique by appending numbers."""
        seen: dict[str, int] = {}
        for comp in components:
            if comp.name in seen:
                seen[comp.name] += 1
                comp.name = f"{comp.name}-{seen[comp.name]}"
            else:
                seen[comp.name] = 1

    # ------------------------------------------------------------------
    # YAML / Graph generation helpers
    # ------------------------------------------------------------------

    def _build_yaml_dict(self, parsed: ParsedInfrastructure) -> dict:
        """Build a dict suitable for YAML output in FaultRay format."""
        components_list = []
        for pc in parsed.components:
            comp_dict = self._parsed_to_yaml_component(pc)
            components_list.append(comp_dict)

        dependencies_list = []
        comp_ids = {c.name for c in parsed.components}
        for pr in parsed.relationships:
            if pr.source in comp_ids and pr.target in comp_ids:
                source_comp = next(
                    c for c in parsed.components if c.name == pr.source
                )
                target_comp = next(
                    c for c in parsed.components if c.name == pr.target
                )
                dep_dict = self._build_dep_dict(pr, source_comp, target_comp)
                dependencies_list.append(dep_dict)

        return {
            "components": components_list,
            "dependencies": dependencies_list,
        }

    def _parsed_to_yaml_component(self, pc: ParsedComponent) -> dict:
        """Convert a ParsedComponent to a YAML component dict."""
        props = pc.properties

        # Build human-readable name
        display_name = pc.name.replace("-", " ").title()
        name = f"{display_name}"

        host = f"{pc.name}.internal"
        port = props.get("port", 8080)

        comp: dict[str, Any] = {
            "id": pc.name,
            "name": name,
            "type": pc.component_type.value,
            "host": host,
            "port": port,
            "replicas": pc.replicas,
        }

        # Capacity
        capacity: dict[str, Any] = {}
        if "max_connections" in props:
            capacity["max_connections"] = props["max_connections"]
        if "max_rps" in props:
            capacity["max_rps"] = props["max_rps"]
        if capacity:
            comp["capacity"] = capacity

        # Metrics (light defaults)
        comp["metrics"] = {
            "cpu_percent": 20,
            "memory_percent": 30,
        }

        # Autoscaling
        if props.get("autoscaling"):
            comp["autoscaling"] = {
                "enabled": True,
                "min_replicas": pc.replicas,
                "max_replicas": pc.replicas * 3,
                "scale_up_threshold": 70.0,
                "scale_down_threshold": 25.0,
            }

        # Failover
        if props.get("failover"):
            comp["failover"] = {
                "enabled": True,
                "promotion_time_seconds": 15.0,
                "health_check_interval_seconds": 5.0,
                "failover_threshold": 3,
            }

        # Security (basic defaults)
        comp["security"] = {
            "encryption_in_transit": True,
            "auth_required": True,
            "log_enabled": True,
        }

        return comp

    def _build_dep_dict(
        self,
        pr: ParsedRelationship,
        source_comp: ParsedComponent,
        target_comp: ParsedComponent,
    ) -> dict:
        """Build a dependency dict for YAML output."""
        protocol = PROTOCOL_MAP.get(
            (source_comp.component_type, target_comp.component_type), "tcp"
        )
        latency = LATENCY_DEFAULTS.get(protocol, 5.0)

        dep: dict[str, Any] = {
            "source": pr.source,
            "target": pr.target,
            "type": pr.relationship_type,
            "weight": 1.0 if pr.relationship_type == "requires" else 0.7,
            "protocol": protocol,
            "latency_ms": latency,
        }

        # Add circuit breaker for critical dependencies
        if (
            pr.relationship_type == "requires"
            and source_comp.properties.get("circuit_breaker")
        ):
            dep["circuit_breaker"] = {
                "enabled": True,
                "failure_threshold": 5,
                "recovery_timeout_seconds": 30.0,
            }

        return dep

    def _parsed_to_component(self, pc: ParsedComponent) -> Component:
        """Convert a ParsedComponent to a FaultRay Component model."""
        from faultray.model.components import (
            AutoScalingConfig,
            Capacity,
            FailoverConfig,
            ResourceMetrics,
            SecurityProfile,
        )

        props = pc.properties
        display_name = pc.name.replace("-", " ").title()

        metrics = ResourceMetrics(cpu_percent=20, memory_percent=30)

        capacity = Capacity(
            max_connections=props.get("max_connections", 1000),
            max_rps=props.get("max_rps", 5000),
        )

        autoscaling = AutoScalingConfig()
        if props.get("autoscaling"):
            autoscaling = AutoScalingConfig(
                enabled=True,
                min_replicas=pc.replicas,
                max_replicas=pc.replicas * 3,
            )

        failover = FailoverConfig()
        if props.get("failover"):
            failover = FailoverConfig(
                enabled=True,
                promotion_time_seconds=15.0,
                health_check_interval_seconds=5.0,
                failover_threshold=3,
            )

        security = SecurityProfile(
            encryption_in_transit=True,
            auth_required=True,
            log_enabled=True,
        )

        return Component(
            id=pc.name,
            name=display_name,
            type=pc.component_type,
            host=f"{pc.name}.internal",
            port=props.get("port", 8080),
            replicas=pc.replicas,
            metrics=metrics,
            capacity=capacity,
            autoscaling=autoscaling,
            failover=failover,
            security=security,
        )
