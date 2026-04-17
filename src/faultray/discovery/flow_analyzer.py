# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""VPC Flow Log / ALB access log analyzer for dependency discovery.

Parses VPC Flow Logs (or file exports) to discover REAL communication
patterns between infrastructure components.  All AWS API calls are
strictly **read-only**.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from faultray.model.components import Dependency
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# VPC Flow Log v2 field order (space-delimited):
# version account-id interface-id srcaddr dstaddr srcport dstport
# protocol packets bytes start end action log-status
_FLOW_LOG_FIELDS = [
    "version",
    "account_id",
    "interface_id",
    "srcaddr",
    "dstaddr",
    "srcport",
    "dstport",
    "protocol",
    "packets",
    "bytes",
    "start",
    "end",
    "action",
    "log_status",
]

# Port-to-dependency-type mapping
_PORT_DEP_MAP: dict[int, tuple[str, str]] = {
    5432: ("database", "requires"),
    3306: ("database", "requires"),
    6379: ("cache", "optional"),
    11211: ("cache", "optional"),
    443: ("web", "requires"),
    80: ("web", "requires"),
}


@dataclass
class CommunicationPattern:
    """A discovered network communication pattern."""

    source_ip: str
    dest_ip: str
    dest_port: int
    protocol: str
    bytes_transferred: int
    request_count: int
    source_component_id: str | None = None
    dest_component_id: str | None = None


@dataclass
class FlowAnalysisResult:
    """Result of analysing flow logs."""

    patterns: list[CommunicationPattern] = field(default_factory=list)
    discovered_dependencies: list[Dependency] = field(default_factory=list)
    unmapped_flows: list[CommunicationPattern] = field(default_factory=list)


class FlowLogAnalyzer:
    """Analyse VPC Flow Logs to discover real communication patterns.

    Maps observed network flows to infrastructure graph components using
    the ``host`` field of each :class:`Component`.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        # Build IP -> component lookup
        self._ip_map: dict[str, str] = {}
        for comp in graph.components.values():
            if comp.host:
                self._ip_map[comp.host] = comp.id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_vpc_flow_logs(
        self,
        log_group: str,
        hours: int = 24,
        *,
        _logs_client: object | None = None,
    ) -> FlowAnalysisResult:
        """Read VPC Flow Logs from CloudWatch Logs (read-only).

        Args:
            log_group: CloudWatch Logs log group name.
            hours: look-back window in hours.
            _logs_client: optional pre-built boto3 Logs client (for DI).

        Returns:
            :class:`FlowAnalysisResult` with patterns and dependencies.
        """
        import datetime

        if _logs_client is None:
            import boto3

            logs = boto3.client("logs")
        else:
            logs = _logs_client

        end_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
        start_ms = end_ms - hours * 3600 * 1000

        raw_lines: list[str] = []

        try:
            # Start query
            query_id = logs.start_query(
                logGroupName=log_group,
                startTime=start_ms,
                endTime=end_ms,
                queryString="fields @message | limit 10000",
            ).get("queryId", "")

            # Poll for results (simplified; production would loop)
            import time

            for _ in range(30):
                result = logs.get_query_results(queryId=query_id)
                status = result.get("status", "")
                if status in ("Complete", "Failed", "Cancelled"):
                    break
                time.sleep(1)

            for row in result.get("results", []):
                for col in row:
                    if col.get("field") == "@message":
                        raw_lines.append(col.get("value", ""))
        except Exception as exc:
            logger.warning("CloudWatch Logs query failed: %s", exc)

        return self._parse_lines(raw_lines)

    def analyze_from_file(self, path: Path) -> FlowAnalysisResult:
        """Parse a flow log file (space-delimited or CSV).

        The first line may be a header (starting with ``version``); if
        so it is skipped.

        Args:
            path: path to the flow log file.

        Returns:
            :class:`FlowAnalysisResult`.
        """
        text = path.read_text()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        # Skip header
        if lines and lines[0].startswith("version"):
            lines = lines[1:]
        return self._parse_lines(lines)

    def merge_dependencies(self, result: FlowAnalysisResult) -> int:
        """Add discovered dependencies to the graph.

        Only dependencies whose source **and** target are mapped to
        known components are added.  Returns the count of dependencies
        added.
        """
        added = 0
        existing_edges: set[tuple[str, str]] = set()
        for edge in self._graph.all_dependency_edges():
            existing_edges.add((edge.source_id, edge.target_id))

        for dep in result.discovered_dependencies:
            key = (dep.source_id, dep.target_id)
            if key in existing_edges:
                continue
            # Verify both components exist
            if (
                self._graph.get_component(dep.source_id) is not None
                and self._graph.get_component(dep.target_id) is not None
            ):
                self._graph.add_dependency(dep)
                existing_edges.add(key)
                added += 1

        return added

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_lines(self, lines: list[str]) -> FlowAnalysisResult:
        """Parse raw flow log lines into patterns and dependencies."""
        # Aggregate flows by (src, dst, dstport, proto)
        aggregated: dict[tuple[str, str, int, str], dict] = {}

        for line in lines:
            parts = line.split()
            if len(parts) < len(_FLOW_LOG_FIELDS):
                continue

            record = dict(zip(_FLOW_LOG_FIELDS, parts))

            # Only count accepted flows
            if record.get("action", "").upper() != "ACCEPT":
                continue

            srcaddr = record["srcaddr"]
            dstaddr = record["dstaddr"]
            try:
                dstport = int(record["dstport"])
                proto_num = int(record["protocol"])
                pkt_bytes = int(record["bytes"])
            except (ValueError, KeyError):
                continue

            proto = self._protocol_name(proto_num)
            key = (srcaddr, dstaddr, dstport, proto)

            if key not in aggregated:
                aggregated[key] = {"bytes": 0, "count": 0}
            aggregated[key]["bytes"] += pkt_bytes
            aggregated[key]["count"] += 1

        # Build patterns
        patterns: list[CommunicationPattern] = []
        discovered: list[Dependency] = []
        unmapped: list[CommunicationPattern] = []

        for (srcaddr, dstaddr, dstport, proto), agg in aggregated.items():
            src_comp = self._ip_map.get(srcaddr)
            dst_comp = self._ip_map.get(dstaddr)

            pattern = CommunicationPattern(
                source_ip=srcaddr,
                dest_ip=dstaddr,
                dest_port=dstport,
                protocol=proto,
                bytes_transferred=agg["bytes"],
                request_count=agg["count"],
                source_component_id=src_comp,
                dest_component_id=dst_comp,
            )
            patterns.append(pattern)

            if src_comp and dst_comp and src_comp != dst_comp:
                dep_type = self._infer_dep_type(dstport)
                dep = Dependency(
                    source_id=src_comp,
                    target_id=dst_comp,
                    dependency_type=dep_type,
                    protocol=proto,
                    port=dstport,
                )
                discovered.append(dep)
            elif src_comp is None or dst_comp is None:
                unmapped.append(pattern)

        return FlowAnalysisResult(
            patterns=patterns,
            discovered_dependencies=discovered,
            unmapped_flows=unmapped,
        )

    @staticmethod
    def _protocol_name(proto_num: int) -> str:
        """Map IANA protocol number to name."""
        return {6: "tcp", 17: "udp", 1: "icmp"}.get(proto_num, str(proto_num))

    @staticmethod
    def _infer_dep_type(port: int) -> str:
        """Infer dependency type from destination port."""
        if port in (5432, 3306):
            return "requires"
        if port in (6379, 11211):
            return "optional"
        if port in (443, 80):
            return "requires"
        return "optional"
