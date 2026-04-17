# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""AI/LLM Infrastructure Resilience Testing.

The first chaos engineering module purpose-built for AI/LLM systems.
Simulates failures in RAG pipelines, AI agents, LLM API gateways,
embedding services, vector databases and more.

Failure modes include token rate-limiting, model timeouts, hallucination
spikes, embedding drift, context-window overflow, GPU OOM, prompt injection,
cold-start latency and fallback-model degradation.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AIComponentType(str, Enum):
    """Types of AI/ML infrastructure components."""

    LLM_API = "llm_api"
    EMBEDDING_SERVICE = "embedding_service"
    VECTOR_DB = "vector_db"
    RAG_PIPELINE = "rag_pipeline"
    AI_AGENT = "ai_agent"
    MODEL_REGISTRY = "model_registry"
    FEATURE_STORE = "feature_store"
    INFERENCE_GATEWAY = "inference_gateway"
    TRAINING_PIPELINE = "training_pipeline"
    PROMPT_CACHE = "prompt_cache"


class AIFailureMode(str, Enum):
    """Failure modes specific to AI/ML infrastructure."""

    TOKEN_RATE_LIMIT = "token_rate_limit"
    MODEL_TIMEOUT = "model_timeout"
    HALLUCINATION_SPIKE = "hallucination_spike"
    EMBEDDING_DRIFT = "embedding_drift"
    CONTEXT_WINDOW_OVERFLOW = "context_window_overflow"
    MODEL_VERSION_MISMATCH = "model_version_mismatch"
    GPU_OOM = "gpu_oom"
    COLD_START_LATENCY = "cold_start_latency"
    PROMPT_INJECTION = "prompt_injection"
    FALLBACK_MODEL_DEGRADATION = "fallback_model_degradation"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class AIComponentConfig(BaseModel):
    """Configuration for a single AI/ML component."""

    component_type: AIComponentType
    model_name: str = ""
    max_tokens_per_min: int = 10000
    p99_latency_ms: float = 500.0
    fallback_model: str = ""
    context_window_size: int = 4096
    embedding_dimension: int = 1536
    gpu_memory_gb: float = 0.0
    replicas: int = 1
    cache_hit_ratio: float = 0.0


class AIResilienceScenario(BaseModel):
    """A single failure scenario to simulate."""

    failure_mode: AIFailureMode
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    target_component_type: AIComponentType = AIComponentType.LLM_API
    duration_seconds: int = 60


class AIGuardrail(BaseModel):
    """A recommended guardrail to protect an AI component."""

    name: str
    description: str
    target_component_type: AIComponentType
    priority: str = "medium"  # low, medium, high, critical


class AIResilienceResult(BaseModel):
    """Result of analysing or simulating resilience for AI components."""

    impact_score: float = Field(default=0.0, ge=0.0, le=100.0)
    degraded_capabilities: list[str] = Field(default_factory=list)
    estimated_user_impact_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    recovery_actions: list[str] = Field(default_factory=list)
    fallback_effectiveness: float = Field(default=0.0, ge=0.0, le=1.0)


class RAGPipelineAssessment(BaseModel):
    """Specialised assessment for RAG (Retrieval-Augmented Generation) pipelines."""

    overall_health_score: float = Field(default=0.0, ge=0.0, le=100.0)
    retrieval_reliability: float = Field(default=0.0, ge=0.0, le=1.0)
    generation_reliability: float = Field(default=0.0, ge=0.0, le=1.0)
    embedding_stability: float = Field(default=0.0, ge=0.0, le=1.0)
    context_utilization: float = Field(default=0.0, ge=0.0, le=1.0)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class AIResilienceReport(BaseModel):
    """Full resilience report for a set of AI components and scenarios."""

    total_components: int = 0
    total_scenarios: int = 0
    overall_resilience_score: float = Field(default=0.0, ge=0.0, le=100.0)
    scenario_results: list[AIResilienceResult] = Field(default_factory=list)
    guardrails: list[AIGuardrail] = Field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Severity / impact helpers
# ---------------------------------------------------------------------------

_FAILURE_BASE_IMPACT: dict[AIFailureMode, float] = {
    AIFailureMode.TOKEN_RATE_LIMIT: 40.0,
    AIFailureMode.MODEL_TIMEOUT: 55.0,
    AIFailureMode.HALLUCINATION_SPIKE: 70.0,
    AIFailureMode.EMBEDDING_DRIFT: 50.0,
    AIFailureMode.CONTEXT_WINDOW_OVERFLOW: 45.0,
    AIFailureMode.MODEL_VERSION_MISMATCH: 35.0,
    AIFailureMode.GPU_OOM: 80.0,
    AIFailureMode.COLD_START_LATENCY: 30.0,
    AIFailureMode.PROMPT_INJECTION: 75.0,
    AIFailureMode.FALLBACK_MODEL_DEGRADATION: 60.0,
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class AIInfraResilienceAnalyzer:
    """Analyses and simulates resilience of AI/LLM infrastructure."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # -- single component analysis -----------------------------------------

    def analyze_component(self, ai_config: AIComponentConfig) -> AIResilienceResult:
        """Analyse resilience posture of a single AI component."""
        degraded: list[str] = []
        recovery: list[str] = []
        impact = 20.0  # baseline

        # Replica factor
        if ai_config.replicas <= 1:
            impact += 15.0
            degraded.append("no_redundancy")
            recovery.append("Add replicas for high availability")

        # Fallback model
        fallback_eff = 0.0
        if ai_config.fallback_model:
            fallback_eff = 0.7
            impact -= 10.0
        else:
            degraded.append("no_fallback")
            recovery.append("Configure a fallback model")

        # Cache
        if ai_config.cache_hit_ratio < 0.3:
            impact += 5.0
            degraded.append("low_cache_hit")
            recovery.append("Implement prompt/result caching")

        # Latency
        if ai_config.p99_latency_ms > 1000:
            impact += 10.0
            degraded.append("high_latency")
            recovery.append("Optimise model serving or add inference replicas")

        # GPU memory
        if ai_config.gpu_memory_gb > 0 and ai_config.gpu_memory_gb < 8:
            impact += 5.0
            degraded.append("limited_gpu")
            recovery.append("Upgrade GPU memory or use model quantisation")

        impact = _clamp(impact)
        user_impact = _clamp(impact * 0.8)

        return AIResilienceResult(
            impact_score=round(impact, 1),
            degraded_capabilities=degraded,
            estimated_user_impact_percent=round(user_impact, 1),
            recovery_actions=recovery,
            fallback_effectiveness=round(fallback_eff, 2),
        )

    # -- failure simulation ------------------------------------------------

    def simulate_failure(
        self,
        scenario: AIResilienceScenario,
        configs: list[AIComponentConfig],
    ) -> AIResilienceResult:
        """Simulate a failure scenario against a set of AI components."""
        if not configs:
            return AIResilienceResult()

        base = _FAILURE_BASE_IMPACT.get(scenario.failure_mode, 50.0)
        impact = base * scenario.severity

        degraded: list[str] = []
        recovery: list[str] = []

        # Find affected configs
        affected = [c for c in configs if c.component_type == scenario.target_component_type]
        if not affected:
            affected = configs  # whole fleet

        has_fallback = any(c.fallback_model for c in affected)
        total_replicas = sum(c.replicas for c in affected)

        # Replica mitigation
        if total_replicas > 1:
            impact *= max(0.3, 1.0 - (total_replicas - 1) * 0.15)

        # Fallback mitigation
        fallback_eff = 0.0
        if has_fallback:
            fallback_eff = 0.6 * (1.0 - scenario.severity * 0.3)
            impact *= 1.0 - fallback_eff * 0.4

        # Failure-mode specific effects
        mode = scenario.failure_mode
        if mode == AIFailureMode.TOKEN_RATE_LIMIT:
            degraded.append("throughput_reduced")
            recovery.append("Increase token quota or add request queuing")
        elif mode == AIFailureMode.MODEL_TIMEOUT:
            degraded.append("response_time_exceeded")
            recovery.append("Reduce model complexity or increase timeout budget")
        elif mode == AIFailureMode.HALLUCINATION_SPIKE:
            degraded.append("output_quality_degraded")
            recovery.append("Enable output validation and guardrails")
        elif mode == AIFailureMode.EMBEDDING_DRIFT:
            degraded.append("retrieval_accuracy_reduced")
            recovery.append("Re-index embeddings with current model version")
        elif mode == AIFailureMode.CONTEXT_WINDOW_OVERFLOW:
            degraded.append("context_truncated")
            recovery.append("Implement chunking or switch to larger context model")
        elif mode == AIFailureMode.MODEL_VERSION_MISMATCH:
            degraded.append("compatibility_broken")
            recovery.append("Pin model versions and use canary deployments")
        elif mode == AIFailureMode.GPU_OOM:
            degraded.append("inference_unavailable")
            recovery.append("Reduce batch size or enable GPU memory offloading")
        elif mode == AIFailureMode.COLD_START_LATENCY:
            degraded.append("startup_delay")
            recovery.append("Use warm pools or pre-loaded model instances")
        elif mode == AIFailureMode.PROMPT_INJECTION:
            degraded.append("security_compromised")
            recovery.append("Deploy input sanitisation and prompt firewalls")
        elif mode == AIFailureMode.FALLBACK_MODEL_DEGRADATION:
            degraded.append("fallback_quality_reduced")
            recovery.append("Test fallback models regularly and set quality thresholds")

        impact = _clamp(impact)
        user_impact = _clamp(impact * 0.85)

        return AIResilienceResult(
            impact_score=round(impact, 1),
            degraded_capabilities=degraded,
            estimated_user_impact_percent=round(user_impact, 1),
            recovery_actions=recovery,
            fallback_effectiveness=round(fallback_eff, 2),
        )

    # -- RAG pipeline assessment -------------------------------------------

    def assess_rag_pipeline(
        self, configs: list[AIComponentConfig]
    ) -> RAGPipelineAssessment:
        """Assess the resilience of a RAG pipeline from its component configs."""
        if not configs:
            return RAGPipelineAssessment()

        risks: list[str] = []
        recommendations: list[str] = []

        # Classify components
        embedders = [c for c in configs if c.component_type == AIComponentType.EMBEDDING_SERVICE]
        vectordbs = [c for c in configs if c.component_type == AIComponentType.VECTOR_DB]
        llms = [c for c in configs if c.component_type == AIComponentType.LLM_API]
        [c for c in configs if c.component_type == AIComponentType.RAG_PIPELINE]

        # Retrieval reliability
        retrieval = 0.8
        if not vectordbs:
            retrieval -= 0.4
            risks.append("No vector database in pipeline")
            recommendations.append("Add a vector database for semantic retrieval")
        else:
            vdb = vectordbs[0]
            if vdb.replicas >= 2:
                retrieval += 0.1
            if vdb.cache_hit_ratio > 0.5:
                retrieval += 0.05

        if not embedders:
            retrieval -= 0.3
            risks.append("No embedding service configured")
            recommendations.append("Add an embedding service")
        else:
            emb = embedders[0]
            if emb.replicas <= 1:
                risks.append("Embedding service has no redundancy")
                recommendations.append("Add replicas to embedding service")

        retrieval = max(0.0, min(1.0, retrieval))

        # Generation reliability
        generation = 0.8
        if not llms:
            generation -= 0.5
            risks.append("No LLM API configured")
            recommendations.append("Configure an LLM API endpoint")
        else:
            llm = llms[0]
            if llm.fallback_model:
                generation += 0.1
            if llm.replicas >= 2:
                generation += 0.05
            if llm.p99_latency_ms > 2000:
                generation -= 0.15
                risks.append("LLM latency exceeds 2s at p99")
                recommendations.append("Optimise LLM serving latency")

        generation = max(0.0, min(1.0, generation))

        # Embedding stability
        embedding_stability = 0.9
        if embedders:
            emb = embedders[0]
            if emb.embedding_dimension < 256:
                embedding_stability -= 0.2
                risks.append("Low embedding dimension may reduce accuracy")
            if emb.replicas <= 1:
                embedding_stability -= 0.1
        else:
            embedding_stability = 0.3

        embedding_stability = max(0.0, min(1.0, embedding_stability))

        # Context utilization
        ctx_util = 0.7
        if llms:
            llm = llms[0]
            if llm.context_window_size >= 32768:
                ctx_util = 0.9
            elif llm.context_window_size >= 8192:
                ctx_util = 0.8
            elif llm.context_window_size < 2048:
                ctx_util = 0.4
                risks.append("Small context window limits RAG effectiveness")
                recommendations.append("Use a model with a larger context window")

        ctx_util = max(0.0, min(1.0, ctx_util))

        # Overall health
        health = (retrieval * 30 + generation * 35 + embedding_stability * 20 + ctx_util * 15)
        health = _clamp(health)

        return RAGPipelineAssessment(
            overall_health_score=round(health, 1),
            retrieval_reliability=round(retrieval, 2),
            generation_reliability=round(generation, 2),
            embedding_stability=round(embedding_stability, 2),
            context_utilization=round(ctx_util, 2),
            risks=risks,
            recommendations=recommendations,
        )

    # -- guardrail recommendations -----------------------------------------

    def recommend_ai_guardrails(
        self, configs: list[AIComponentConfig]
    ) -> list[AIGuardrail]:
        """Recommend guardrails for the given AI component configurations."""
        guardrails: list[AIGuardrail] = []

        seen_types: set[AIComponentType] = set()
        for cfg in configs:
            if cfg.component_type in seen_types:
                continue
            seen_types.add(cfg.component_type)

            ct = cfg.component_type

            if ct == AIComponentType.LLM_API:
                guardrails.append(AIGuardrail(
                    name="Token Rate Limiter",
                    description="Enforce per-user and per-request token limits",
                    target_component_type=ct,
                    priority="high",
                ))
                guardrails.append(AIGuardrail(
                    name="Output Validator",
                    description="Validate LLM outputs against schema and safety rules",
                    target_component_type=ct,
                    priority="critical",
                ))

            if ct == AIComponentType.EMBEDDING_SERVICE:
                guardrails.append(AIGuardrail(
                    name="Embedding Drift Monitor",
                    description="Detect and alert on embedding distribution shifts",
                    target_component_type=ct,
                    priority="medium",
                ))

            if ct == AIComponentType.VECTOR_DB:
                guardrails.append(AIGuardrail(
                    name="Index Health Check",
                    description="Periodically validate vector index integrity and recall",
                    target_component_type=ct,
                    priority="high",
                ))

            if ct == AIComponentType.RAG_PIPELINE:
                guardrails.append(AIGuardrail(
                    name="Retrieval Quality Gate",
                    description="Enforce minimum relevance score for retrieved documents",
                    target_component_type=ct,
                    priority="high",
                ))

            if ct == AIComponentType.AI_AGENT:
                guardrails.append(AIGuardrail(
                    name="Action Sandbox",
                    description="Restrict agent actions to a safe allow-list",
                    target_component_type=ct,
                    priority="critical",
                ))

            if ct == AIComponentType.INFERENCE_GATEWAY:
                guardrails.append(AIGuardrail(
                    name="Request Throttle",
                    description="Apply adaptive rate limiting at the inference gateway",
                    target_component_type=ct,
                    priority="high",
                ))

            if ct == AIComponentType.PROMPT_CACHE:
                guardrails.append(AIGuardrail(
                    name="Cache Invalidation Policy",
                    description="Evict stale prompt cache entries on model update",
                    target_component_type=ct,
                    priority="medium",
                ))

            if ct == AIComponentType.MODEL_REGISTRY:
                guardrails.append(AIGuardrail(
                    name="Version Pinning",
                    description="Enforce explicit model version pinning in deployments",
                    target_component_type=ct,
                    priority="high",
                ))

            if ct == AIComponentType.FEATURE_STORE:
                guardrails.append(AIGuardrail(
                    name="Feature Freshness Monitor",
                    description="Alert when feature store data exceeds staleness threshold",
                    target_component_type=ct,
                    priority="medium",
                ))

            if ct == AIComponentType.TRAINING_PIPELINE:
                guardrails.append(AIGuardrail(
                    name="Training Data Validator",
                    description="Validate training data quality and detect poisoning",
                    target_component_type=ct,
                    priority="critical",
                ))

        return guardrails

    # -- full report -------------------------------------------------------

    def generate_report(
        self,
        configs: list[AIComponentConfig],
        scenarios: list[AIResilienceScenario],
    ) -> AIResilienceReport:
        """Generate a comprehensive resilience report."""
        results: list[AIResilienceResult] = []
        for scenario in scenarios:
            results.append(self.simulate_failure(scenario, configs))

        guardrails = self.recommend_ai_guardrails(configs)

        if results:
            avg_impact = sum(r.impact_score for r in results) / len(results)
            overall = _clamp(100.0 - avg_impact)
        else:
            overall = 100.0 if configs else 0.0

        total_degraded = set()
        for r in results:
            total_degraded.update(r.degraded_capabilities)

        summary_parts: list[str] = [
            f"Analysed {len(configs)} AI component(s) across {len(scenarios)} scenario(s).",
        ]
        if total_degraded:
            summary_parts.append(
                f"Degraded capabilities: {', '.join(sorted(total_degraded))}."
            )
        summary_parts.append(f"Overall resilience score: {round(overall, 1)}/100.")

        return AIResilienceReport(
            total_components=len(configs),
            total_scenarios=len(scenarios),
            overall_resilience_score=round(overall, 1),
            scenario_results=results,
            guardrails=guardrails,
            summary=" ".join(summary_parts),
        )
