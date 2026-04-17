# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Automatic infrastructure discovery from APM agent data + cloud APIs.

Combines:
- Local discovery: processes, ports, connections (from psutil via APM agent)
- Cloud discovery: AWS/GCP/Azure managed services (from existing scanners)
- Topology inference: dependency relationships from connection data
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from faultray.model.components import ComponentType, Dependency
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# Default path for persisting the auto-discovered model
_DEFAULT_MODEL_PATH = Path.home() / ".faultray" / "auto-model.json"


class AutoDiscoverer:
    """Bridges APM agent data and cloud scanners into a unified InfraGraph.

    Performs local discovery via psutil and optionally enriches the topology
    with cloud-managed services discovered through existing provider scanners.
    """

    def __init__(
        self,
        cloud_provider: str | None = None,
        cloud_config: dict[str, Any] | None = None,
        model_output_path: str = "",
    ) -> None:
        """Initialise the discoverer.

        Parameters
        ----------
        cloud_provider:
            ``"aws"``, ``"gcp"``, ``"azure"``, or ``None`` (local only).
        cloud_config:
            Provider-specific configuration dictionary.
            - AWS: ``{"region": "ap-northeast-1", "profile": "default"}``
            - GCP: ``{"project_id": "my-project"}``
            - Azure: ``{"subscription_id": "...", "resource_group": "..."}``
        model_output_path:
            Path where the discovered model JSON is saved.  Defaults to
            ``~/.faultray/auto-model.json``.
        """
        self.cloud_provider = cloud_provider
        self.cloud_config: dict[str, Any] = cloud_config or {}
        self._output_path = (
            Path(model_output_path) if model_output_path else _DEFAULT_MODEL_PATH
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def discover_local(self) -> InfraGraph:
        """Discover local services using psutil.

        Delegates to :func:`faultray.discovery.scanner.scan_local` and
        returns the resulting :class:`InfraGraph`.
        """
        from faultray.discovery.scanner import scan_local

        logger.debug("Starting local infrastructure discovery via psutil")
        try:
            graph = scan_local()
            logger.info(
                "Local discovery complete: %d components found",
                len(graph.components),
            )
        except Exception as exc:
            logger.warning("Local discovery failed (%s) — returning empty graph", exc)
            graph = InfraGraph()
        return graph

    def discover_cloud(self) -> InfraGraph | None:
        """Discover cloud managed services using existing provider scanners.

        Returns ``None`` when no cloud provider is configured or when the
        required SDK is not installed.
        """
        if not self.cloud_provider:
            return None

        provider = self.cloud_provider.lower()
        logger.debug("Starting cloud discovery for provider: %s", provider)

        try:
            if provider == "aws":
                return self._discover_aws()
            if provider == "gcp":
                return self._discover_gcp()
            if provider == "azure":
                return self._discover_azure()

            logger.warning("Unknown cloud provider '%s' — skipping cloud discovery", provider)
        except ImportError as exc:
            logger.warning(
                "Cloud discovery skipped — required SDK not installed: %s", exc
            )
        except Exception as exc:
            logger.warning("Cloud discovery failed (%s) — skipping", exc)

        return None

    def discover_all(self) -> InfraGraph:
        """Combined discovery: local + cloud → unified InfraGraph.

        Steps:
        1. Run local discovery (fast, <5 s).
        2. Run cloud discovery if configured (may take 10–30 s).
        3. Merge graphs and infer cross-environment dependencies.
        4. Persist the unified model to disk.
        """
        local_graph = self.discover_local()
        cloud_graph = self.discover_cloud()

        if cloud_graph is not None:
            unified = self.merge_graphs(local_graph, cloud_graph)
        else:
            unified = local_graph

        self._save_model(unified)
        return unified

    def merge_graphs(self, local: InfraGraph, cloud: InfraGraph) -> InfraGraph:
        """Merge local and cloud graphs, deduplicating overlapping components.

        Deduplication is based on component ID.  Local components take
        precedence when a collision is detected.
        """
        merged = InfraGraph()

        # Add all local components first (they have priority)
        for comp in local.components.values():
            merged.add_component(comp)

        # Add cloud components, skipping duplicates
        for comp in cloud.components.values():
            if comp.id not in merged.components:
                merged.add_component(comp)
            else:
                logger.debug(
                    "Deduplicating component '%s' (local takes priority)", comp.id
                )

        # Copy all dependency edges from both graphs
        for dep in local.all_dependency_edges():
            if (
                dep.source_id in merged.components
                and dep.target_id in merged.components
            ):
                merged.add_dependency(dep)

        for dep in cloud.all_dependency_edges():
            if (
                dep.source_id in merged.components
                and dep.target_id in merged.components
            ):
                # Only add if edge does not already exist
                existing = merged.get_dependency_edge(dep.source_id, dep.target_id)
                if existing is None:
                    merged.add_dependency(dep)

        # Infer cross-environment dependencies (local ↔ cloud)
        self._infer_cross_deps(merged, local, cloud)

        logger.info(
            "Graph merge complete: %d components, %d dependencies",
            len(merged.components),
            len(merged.all_dependency_edges()),
        )
        return merged

    # ------------------------------------------------------------------
    # Private: cloud scanners
    # ------------------------------------------------------------------

    def _discover_aws(self) -> InfraGraph:
        """Run AWS scanner and return the resulting InfraGraph."""
        from faultray.discovery.aws_scanner import AWSScanner

        region = self.cloud_config.get("region", "ap-northeast-1")
        profile = self.cloud_config.get("profile") or None
        scanner = AWSScanner(region=str(region), profile=profile)
        result = scanner.scan()
        logger.info(
            "AWS discovery complete: %d components, %d dependencies",
            result.components_found,
            result.dependencies_inferred,
        )
        return result.graph

    def _discover_gcp(self) -> InfraGraph:
        """Run GCP scanner and return the resulting InfraGraph."""
        from faultray.discovery.gcp_scanner import GCPScanner

        project_id = self.cloud_config.get("project_id", "")
        scanner = GCPScanner(project_id=str(project_id))
        result = scanner.scan()
        logger.info(
            "GCP discovery complete: %d components, %d dependencies",
            result.components_found,
            result.dependencies_inferred,
        )
        return result.graph

    def _discover_azure(self) -> InfraGraph:
        """Run Azure scanner and return the resulting InfraGraph."""
        from faultray.discovery.azure_scanner import AzureScanner

        subscription_id = self.cloud_config.get("subscription_id", "")
        resource_group = self.cloud_config.get("resource_group") or None
        scanner = AzureScanner(
            subscription_id=str(subscription_id),
            resource_group=resource_group,
        )
        result = scanner.scan()
        logger.info(
            "Azure discovery complete: %d components, %d dependencies",
            result.components_found,
            result.dependencies_inferred,
        )
        return result.graph

    # ------------------------------------------------------------------
    # Private: cross-environment dependency inference
    # ------------------------------------------------------------------

    def _infer_cross_deps(
        self,
        merged: InfraGraph,
        local: InfraGraph,
        cloud: InfraGraph,
    ) -> None:
        """Infer dependencies between local and cloud components.

        Heuristic: if a local APP_SERVER component exists and there are
        cloud DATABASE / CACHE components, assume the app server depends on
        them (requires relationship).  This is a best-effort inference based
        on component types.
        """
        local_ids = set(local.components)
        cloud_ids = set(cloud.components)

        local_app_servers = [
            comp
            for cid, comp in merged.components.items()
            if cid in local_ids and comp.type == ComponentType.APP_SERVER
        ]
        cloud_data_services = [
            comp
            for cid, comp in merged.components.items()
            if cid in cloud_ids
            and comp.type in (ComponentType.DATABASE, ComponentType.CACHE, ComponentType.QUEUE)
        ]

        for app in local_app_servers:
            for svc in cloud_data_services:
                existing = merged.get_dependency_edge(app.id, svc.id)
                if existing is None:
                    dep = Dependency(
                        source_id=app.id,
                        target_id=svc.id,
                        dependency_type="requires",
                        label=f"inferred:{app.type.value}→{svc.type.value}",
                    )
                    merged.add_dependency(dep)
                    logger.debug(
                        "Inferred cross-env dependency: %s → %s", app.id, svc.id
                    )

    # ------------------------------------------------------------------
    # Private: persistence
    # ------------------------------------------------------------------

    def _save_model(self, graph: InfraGraph) -> None:
        """Persist the unified InfraGraph to disk as JSON."""
        try:
            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            graph.save(self._output_path)
            logger.debug("Auto-discovered model saved to %s", self._output_path)
        except Exception as exc:
            logger.warning("Failed to save auto-model to %s: %s", self._output_path, exc)
