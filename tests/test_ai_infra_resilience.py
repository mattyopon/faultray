"""Tests for AI/LLM Infrastructure Resilience Testing module."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, FailoverConfig, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.ai_infra_resilience import (
    AIComponentConfig,
    AIComponentType,
    AIFailureMode,
    AIGuardrail,
    AIInfraResilienceAnalyzer,
    AIResilienceReport,
    AIResilienceResult,
    AIResilienceScenario,
    RAGPipelineAssessment,
    _clamp,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover = FailoverConfig(enabled=True, promotion_time_seconds=10)
    return c


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _analyzer(graph: InfraGraph | None = None) -> AIInfraResilienceAnalyzer:
    if graph is None:
        graph = _graph(_comp("a1", "app"))
    return AIInfraResilienceAnalyzer(graph)


def _default_config(**kw) -> AIComponentConfig:
    kw.setdefault("component_type", AIComponentType.LLM_API)
    return AIComponentConfig(**kw)


def _rag_configs(
    *,
    llm: bool = True,
    embedder: bool = True,
    vectordb: bool = True,
    pipeline: bool = True,
    llm_kw: dict | None = None,
    emb_kw: dict | None = None,
    vdb_kw: dict | None = None,
) -> list[AIComponentConfig]:
    """Build a typical RAG component list."""
    cfgs: list[AIComponentConfig] = []
    if llm:
        kw = {"component_type": AIComponentType.LLM_API, "model_name": "gpt-4"}
        kw.update(llm_kw or {})
        cfgs.append(AIComponentConfig(**kw))
    if embedder:
        kw = {"component_type": AIComponentType.EMBEDDING_SERVICE}
        kw.update(emb_kw or {})
        cfgs.append(AIComponentConfig(**kw))
    if vectordb:
        kw = {"component_type": AIComponentType.VECTOR_DB}
        kw.update(vdb_kw or {})
        cfgs.append(AIComponentConfig(**kw))
    if pipeline:
        cfgs.append(AIComponentConfig(component_type=AIComponentType.RAG_PIPELINE))
    return cfgs


# ===================================================================
# 1. Enum value tests
# ===================================================================


class TestAIComponentTypeEnum:
    """Verify all AIComponentType enum members."""

    @pytest.mark.parametrize(
        "member,value",
        [
            (AIComponentType.LLM_API, "llm_api"),
            (AIComponentType.EMBEDDING_SERVICE, "embedding_service"),
            (AIComponentType.VECTOR_DB, "vector_db"),
            (AIComponentType.RAG_PIPELINE, "rag_pipeline"),
            (AIComponentType.AI_AGENT, "ai_agent"),
            (AIComponentType.MODEL_REGISTRY, "model_registry"),
            (AIComponentType.FEATURE_STORE, "feature_store"),
            (AIComponentType.INFERENCE_GATEWAY, "inference_gateway"),
            (AIComponentType.TRAINING_PIPELINE, "training_pipeline"),
            (AIComponentType.PROMPT_CACHE, "prompt_cache"),
        ],
    )
    def test_member_value(self, member, value):
        assert member.value == value

    def test_total_members(self):
        assert len(AIComponentType) == 10


class TestAIFailureModeEnum:
    """Verify all AIFailureMode enum members."""

    @pytest.mark.parametrize(
        "member,value",
        [
            (AIFailureMode.TOKEN_RATE_LIMIT, "token_rate_limit"),
            (AIFailureMode.MODEL_TIMEOUT, "model_timeout"),
            (AIFailureMode.HALLUCINATION_SPIKE, "hallucination_spike"),
            (AIFailureMode.EMBEDDING_DRIFT, "embedding_drift"),
            (AIFailureMode.CONTEXT_WINDOW_OVERFLOW, "context_window_overflow"),
            (AIFailureMode.MODEL_VERSION_MISMATCH, "model_version_mismatch"),
            (AIFailureMode.GPU_OOM, "gpu_oom"),
            (AIFailureMode.COLD_START_LATENCY, "cold_start_latency"),
            (AIFailureMode.PROMPT_INJECTION, "prompt_injection"),
            (AIFailureMode.FALLBACK_MODEL_DEGRADATION, "fallback_model_degradation"),
        ],
    )
    def test_member_value(self, member, value):
        assert member.value == value

    def test_total_members(self):
        assert len(AIFailureMode) == 10


# ===================================================================
# 2. AIComponentConfig tests
# ===================================================================


class TestAIComponentConfig:
    def test_defaults(self):
        cfg = _default_config()
        assert cfg.component_type == AIComponentType.LLM_API
        assert cfg.model_name == ""
        assert cfg.max_tokens_per_min == 10000
        assert cfg.p99_latency_ms == 500.0
        assert cfg.fallback_model == ""
        assert cfg.context_window_size == 4096
        assert cfg.embedding_dimension == 1536
        assert cfg.gpu_memory_gb == 0.0
        assert cfg.replicas == 1
        assert cfg.cache_hit_ratio == 0.0

    def test_custom_values(self):
        cfg = AIComponentConfig(
            component_type=AIComponentType.EMBEDDING_SERVICE,
            model_name="text-embedding-ada-002",
            max_tokens_per_min=50000,
            p99_latency_ms=100.0,
            fallback_model="fallback-embed",
            context_window_size=8192,
            embedding_dimension=768,
            gpu_memory_gb=24.0,
            replicas=3,
            cache_hit_ratio=0.85,
        )
        assert cfg.component_type == AIComponentType.EMBEDDING_SERVICE
        assert cfg.model_name == "text-embedding-ada-002"
        assert cfg.replicas == 3
        assert cfg.cache_hit_ratio == 0.85

    def test_zero_replicas(self):
        # Unlike Component, AIComponentConfig doesn't have a validator
        cfg = _default_config(replicas=0)
        assert cfg.replicas == 0

    def test_large_context_window(self):
        cfg = _default_config(context_window_size=128000)
        assert cfg.context_window_size == 128000


# ===================================================================
# 3. AIResilienceScenario tests
# ===================================================================


class TestAIResilienceScenario:
    def test_defaults(self):
        s = AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM)
        assert s.severity == 0.5
        assert s.target_component_type == AIComponentType.LLM_API
        assert s.duration_seconds == 60

    def test_severity_bounds(self):
        s = AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=0.0)
        assert s.severity == 0.0
        s2 = AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=1.0)
        assert s2.severity == 1.0

    def test_severity_out_of_range(self):
        with pytest.raises(Exception):
            AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=1.5)

    def test_negative_severity(self):
        with pytest.raises(Exception):
            AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=-0.1)


# ===================================================================
# 4. AIResilienceResult tests
# ===================================================================


class TestAIResilienceResult:
    def test_defaults(self):
        r = AIResilienceResult()
        assert r.impact_score == 0.0
        assert r.degraded_capabilities == []
        assert r.estimated_user_impact_percent == 0.0
        assert r.recovery_actions == []
        assert r.fallback_effectiveness == 0.0

    def test_custom(self):
        r = AIResilienceResult(
            impact_score=75.0,
            degraded_capabilities=["accuracy"],
            estimated_user_impact_percent=60.0,
            recovery_actions=["restart"],
            fallback_effectiveness=0.5,
        )
        assert r.impact_score == 75.0
        assert len(r.degraded_capabilities) == 1


# ===================================================================
# 5. RAGPipelineAssessment tests
# ===================================================================


class TestRAGPipelineAssessment:
    def test_defaults(self):
        a = RAGPipelineAssessment()
        assert a.overall_health_score == 0.0
        assert a.retrieval_reliability == 0.0
        assert a.generation_reliability == 0.0
        assert a.embedding_stability == 0.0
        assert a.context_utilization == 0.0
        assert a.risks == []
        assert a.recommendations == []


# ===================================================================
# 6. AIGuardrail tests
# ===================================================================


class TestAIGuardrail:
    def test_defaults(self):
        g = AIGuardrail(
            name="g1",
            description="desc",
            target_component_type=AIComponentType.LLM_API,
        )
        assert g.priority == "medium"

    def test_custom_priority(self):
        g = AIGuardrail(
            name="g2",
            description="d",
            target_component_type=AIComponentType.AI_AGENT,
            priority="critical",
        )
        assert g.priority == "critical"


# ===================================================================
# 7. AIResilienceReport tests
# ===================================================================


class TestAIResilienceReport:
    def test_defaults(self):
        rpt = AIResilienceReport()
        assert rpt.total_components == 0
        assert rpt.total_scenarios == 0
        assert rpt.overall_resilience_score == 0.0
        assert rpt.scenario_results == []
        assert rpt.guardrails == []
        assert rpt.summary == ""


# ===================================================================
# 8. _clamp helper tests
# ===================================================================


class TestClamp:
    def test_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_below_low(self):
        assert _clamp(-10.0) == 0.0

    def test_above_high(self):
        assert _clamp(110.0) == 100.0

    def test_at_boundaries(self):
        assert _clamp(0.0) == 0.0
        assert _clamp(100.0) == 100.0

    def test_custom_bounds(self):
        assert _clamp(5.0, lo=0.0, hi=1.0) == 1.0
        assert _clamp(-5.0, lo=-1.0, hi=1.0) == -1.0


# ===================================================================
# 9. AIInfraResilienceAnalyzer — __init__
# ===================================================================


class TestAnalyzerInit:
    def test_init_stores_graph(self):
        g = _graph(_comp("x", "x"))
        a = AIInfraResilienceAnalyzer(g)
        assert a._graph is g

    def test_init_empty_graph(self):
        g = InfraGraph()
        a = AIInfraResilienceAnalyzer(g)
        assert a._graph is g


# ===================================================================
# 10. analyze_component tests
# ===================================================================


class TestAnalyzeComponent:
    def test_single_replica_no_fallback(self):
        a = _analyzer()
        cfg = _default_config(replicas=1, fallback_model="")
        result = a.analyze_component(cfg)
        assert "no_redundancy" in result.degraded_capabilities
        assert "no_fallback" in result.degraded_capabilities
        assert result.fallback_effectiveness == 0.0
        assert result.impact_score > 30

    def test_multi_replica_with_fallback(self):
        a = _analyzer()
        cfg = _default_config(replicas=3, fallback_model="gpt-3.5")
        result = a.analyze_component(cfg)
        assert "no_redundancy" not in result.degraded_capabilities
        assert "no_fallback" not in result.degraded_capabilities
        assert result.fallback_effectiveness == 0.7
        assert result.impact_score < 30

    def test_low_cache_hit(self):
        a = _analyzer()
        cfg = _default_config(cache_hit_ratio=0.1)
        result = a.analyze_component(cfg)
        assert "low_cache_hit" in result.degraded_capabilities

    def test_high_cache_hit(self):
        a = _analyzer()
        cfg = _default_config(cache_hit_ratio=0.9)
        result = a.analyze_component(cfg)
        assert "low_cache_hit" not in result.degraded_capabilities

    def test_high_latency(self):
        a = _analyzer()
        cfg = _default_config(p99_latency_ms=2000)
        result = a.analyze_component(cfg)
        assert "high_latency" in result.degraded_capabilities

    def test_low_latency(self):
        a = _analyzer()
        cfg = _default_config(p99_latency_ms=200)
        result = a.analyze_component(cfg)
        assert "high_latency" not in result.degraded_capabilities

    def test_limited_gpu(self):
        a = _analyzer()
        cfg = _default_config(gpu_memory_gb=4.0)
        result = a.analyze_component(cfg)
        assert "limited_gpu" in result.degraded_capabilities

    def test_no_gpu(self):
        a = _analyzer()
        cfg = _default_config(gpu_memory_gb=0.0)
        result = a.analyze_component(cfg)
        assert "limited_gpu" not in result.degraded_capabilities

    def test_adequate_gpu(self):
        a = _analyzer()
        cfg = _default_config(gpu_memory_gb=16.0)
        result = a.analyze_component(cfg)
        assert "limited_gpu" not in result.degraded_capabilities

    def test_recovery_actions_populated(self):
        a = _analyzer()
        cfg = _default_config(replicas=1, fallback_model="", cache_hit_ratio=0.1, p99_latency_ms=2000, gpu_memory_gb=4.0)
        result = a.analyze_component(cfg)
        assert len(result.recovery_actions) >= 4

    def test_user_impact_proportional(self):
        a = _analyzer()
        cfg = _default_config()
        result = a.analyze_component(cfg)
        assert result.estimated_user_impact_percent <= result.impact_score

    def test_impact_score_clamped(self):
        a = _analyzer()
        # Many bad factors => score should still be <= 100
        cfg = _default_config(
            replicas=1, fallback_model="", cache_hit_ratio=0.0,
            p99_latency_ms=5000, gpu_memory_gb=2.0,
        )
        result = a.analyze_component(cfg)
        assert 0 <= result.impact_score <= 100

    def test_best_case(self):
        a = _analyzer()
        cfg = _default_config(
            replicas=5, fallback_model="fb", cache_hit_ratio=0.9,
            p99_latency_ms=50, gpu_memory_gb=80.0,
        )
        result = a.analyze_component(cfg)
        assert result.impact_score < 20


# ===================================================================
# 11. simulate_failure tests
# ===================================================================


class TestSimulateFailure:
    def test_empty_configs(self):
        a = _analyzer()
        scenario = AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM)
        result = a.simulate_failure(scenario, [])
        assert result.impact_score == 0.0

    def test_zero_severity(self):
        a = _analyzer()
        scenario = AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=0.0)
        result = a.simulate_failure(scenario, [_default_config()])
        assert result.impact_score == 0.0

    def test_max_severity(self):
        a = _analyzer()
        scenario = AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=1.0)
        result = a.simulate_failure(scenario, [_default_config()])
        assert result.impact_score > 0

    def test_replica_mitigation(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.MODEL_TIMEOUT, severity=0.8)
        single = a.simulate_failure(s, [_default_config(replicas=1)])
        multi = a.simulate_failure(s, [_default_config(replicas=5)])
        assert multi.impact_score < single.impact_score

    def test_fallback_mitigation(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.TOKEN_RATE_LIMIT, severity=0.7)
        no_fb = a.simulate_failure(s, [_default_config(fallback_model="")])
        with_fb = a.simulate_failure(s, [_default_config(fallback_model="gpt-3.5")])
        assert with_fb.impact_score <= no_fb.impact_score
        assert with_fb.fallback_effectiveness > 0

    @pytest.mark.parametrize("mode", list(AIFailureMode))
    def test_all_failure_modes_produce_degraded(self, mode):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=mode, severity=0.5)
        result = a.simulate_failure(s, [_default_config()])
        assert len(result.degraded_capabilities) >= 1

    @pytest.mark.parametrize("mode", list(AIFailureMode))
    def test_all_failure_modes_produce_recovery_actions(self, mode):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=mode, severity=0.5)
        result = a.simulate_failure(s, [_default_config()])
        assert len(result.recovery_actions) >= 1

    def test_targeted_component(self):
        a = _analyzer()
        s = AIResilienceScenario(
            failure_mode=AIFailureMode.EMBEDDING_DRIFT,
            severity=0.6,
            target_component_type=AIComponentType.EMBEDDING_SERVICE,
        )
        cfgs = [
            _default_config(component_type=AIComponentType.EMBEDDING_SERVICE, replicas=3),
            _default_config(component_type=AIComponentType.LLM_API, replicas=1),
        ]
        result = a.simulate_failure(s, cfgs)
        assert "retrieval_accuracy_reduced" in result.degraded_capabilities

    def test_no_matching_target_uses_all(self):
        a = _analyzer()
        s = AIResilienceScenario(
            failure_mode=AIFailureMode.GPU_OOM,
            severity=0.5,
            target_component_type=AIComponentType.TRAINING_PIPELINE,
        )
        cfgs = [_default_config(component_type=AIComponentType.LLM_API)]
        result = a.simulate_failure(s, cfgs)
        # Should still produce a result
        assert result.impact_score > 0

    def test_token_rate_limit_degradation(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.TOKEN_RATE_LIMIT, severity=0.5)
        r = a.simulate_failure(s, [_default_config()])
        assert "throughput_reduced" in r.degraded_capabilities

    def test_model_timeout_degradation(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.MODEL_TIMEOUT, severity=0.5)
        r = a.simulate_failure(s, [_default_config()])
        assert "response_time_exceeded" in r.degraded_capabilities

    def test_hallucination_spike_degradation(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.HALLUCINATION_SPIKE, severity=0.5)
        r = a.simulate_failure(s, [_default_config()])
        assert "output_quality_degraded" in r.degraded_capabilities

    def test_embedding_drift_degradation(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.EMBEDDING_DRIFT, severity=0.5)
        r = a.simulate_failure(s, [_default_config()])
        assert "retrieval_accuracy_reduced" in r.degraded_capabilities

    def test_context_window_overflow_degradation(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.CONTEXT_WINDOW_OVERFLOW, severity=0.5)
        r = a.simulate_failure(s, [_default_config()])
        assert "context_truncated" in r.degraded_capabilities

    def test_model_version_mismatch_degradation(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.MODEL_VERSION_MISMATCH, severity=0.5)
        r = a.simulate_failure(s, [_default_config()])
        assert "compatibility_broken" in r.degraded_capabilities

    def test_gpu_oom_degradation(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=0.5)
        r = a.simulate_failure(s, [_default_config()])
        assert "inference_unavailable" in r.degraded_capabilities

    def test_cold_start_latency_degradation(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.COLD_START_LATENCY, severity=0.5)
        r = a.simulate_failure(s, [_default_config()])
        assert "startup_delay" in r.degraded_capabilities

    def test_prompt_injection_degradation(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.PROMPT_INJECTION, severity=0.5)
        r = a.simulate_failure(s, [_default_config()])
        assert "security_compromised" in r.degraded_capabilities

    def test_fallback_model_degradation_degradation(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.FALLBACK_MODEL_DEGRADATION, severity=0.5)
        r = a.simulate_failure(s, [_default_config()])
        assert "fallback_quality_reduced" in r.degraded_capabilities

    def test_impact_clamped_max(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=1.0)
        r = a.simulate_failure(s, [_default_config()])
        assert r.impact_score <= 100.0

    def test_user_impact_proportional(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=0.8)
        r = a.simulate_failure(s, [_default_config()])
        assert r.estimated_user_impact_percent <= r.impact_score * 0.86


# ===================================================================
# 12. assess_rag_pipeline tests
# ===================================================================


class TestAssessRAGPipeline:
    def test_empty_configs(self):
        a = _analyzer()
        result = a.assess_rag_pipeline([])
        assert result.overall_health_score == 0.0

    def test_full_rag_pipeline(self):
        a = _analyzer()
        cfgs = _rag_configs()
        result = a.assess_rag_pipeline(cfgs)
        assert result.overall_health_score > 50
        assert result.retrieval_reliability > 0
        assert result.generation_reliability > 0
        assert result.embedding_stability > 0
        assert result.context_utilization > 0

    def test_missing_vectordb(self):
        a = _analyzer()
        cfgs = _rag_configs(vectordb=False)
        result = a.assess_rag_pipeline(cfgs)
        assert "No vector database in pipeline" in result.risks

    def test_missing_embedder(self):
        a = _analyzer()
        cfgs = _rag_configs(embedder=False)
        result = a.assess_rag_pipeline(cfgs)
        assert "No embedding service configured" in result.risks

    def test_missing_llm(self):
        a = _analyzer()
        cfgs = _rag_configs(llm=False)
        result = a.assess_rag_pipeline(cfgs)
        assert "No LLM API configured" in result.risks

    def test_high_llm_latency(self):
        a = _analyzer()
        cfgs = _rag_configs(llm_kw={"p99_latency_ms": 3000})
        result = a.assess_rag_pipeline(cfgs)
        assert "LLM latency exceeds 2s at p99" in result.risks

    def test_llm_with_fallback_improves_generation(self):
        a = _analyzer()
        no_fb = a.assess_rag_pipeline(_rag_configs(llm_kw={"fallback_model": ""}))
        with_fb = a.assess_rag_pipeline(_rag_configs(llm_kw={"fallback_model": "gpt-3.5"}))
        assert with_fb.generation_reliability >= no_fb.generation_reliability

    def test_multi_replica_embedder(self):
        a = _analyzer()
        single = a.assess_rag_pipeline(_rag_configs(emb_kw={"replicas": 1}))
        multi = a.assess_rag_pipeline(_rag_configs(emb_kw={"replicas": 3}))
        assert multi.embedding_stability >= single.embedding_stability

    def test_embedder_single_replica_risk(self):
        a = _analyzer()
        result = a.assess_rag_pipeline(_rag_configs(emb_kw={"replicas": 1}))
        assert "Embedding service has no redundancy" in result.risks

    def test_low_embedding_dimension(self):
        a = _analyzer()
        result = a.assess_rag_pipeline(_rag_configs(emb_kw={"embedding_dimension": 128}))
        assert "Low embedding dimension may reduce accuracy" in result.risks

    def test_large_context_window(self):
        a = _analyzer()
        result = a.assess_rag_pipeline(_rag_configs(llm_kw={"context_window_size": 128000}))
        assert result.context_utilization >= 0.9

    def test_medium_context_window(self):
        a = _analyzer()
        result = a.assess_rag_pipeline(_rag_configs(llm_kw={"context_window_size": 8192}))
        assert result.context_utilization == 0.8

    def test_small_context_window(self):
        a = _analyzer()
        result = a.assess_rag_pipeline(_rag_configs(llm_kw={"context_window_size": 1024}))
        assert "Small context window limits RAG effectiveness" in result.risks

    def test_vectordb_multi_replica_improves_retrieval(self):
        a = _analyzer()
        single = a.assess_rag_pipeline(_rag_configs(vdb_kw={"replicas": 1}))
        multi = a.assess_rag_pipeline(_rag_configs(vdb_kw={"replicas": 2}))
        assert multi.retrieval_reliability >= single.retrieval_reliability

    def test_vectordb_high_cache_improves_retrieval(self):
        a = _analyzer()
        low = a.assess_rag_pipeline(_rag_configs(vdb_kw={"cache_hit_ratio": 0.1}))
        high = a.assess_rag_pipeline(_rag_configs(vdb_kw={"cache_hit_ratio": 0.9}))
        assert high.retrieval_reliability >= low.retrieval_reliability

    def test_llm_multi_replica(self):
        a = _analyzer()
        single = a.assess_rag_pipeline(_rag_configs(llm_kw={"replicas": 1}))
        multi = a.assess_rag_pipeline(_rag_configs(llm_kw={"replicas": 3}))
        assert multi.generation_reliability >= single.generation_reliability

    def test_no_components_at_all(self):
        a = _analyzer()
        result = a.assess_rag_pipeline(
            _rag_configs(llm=False, embedder=False, vectordb=False, pipeline=False)
        )
        assert result.overall_health_score == 0.0

    def test_only_pipeline_component(self):
        a = _analyzer()
        cfgs = [AIComponentConfig(component_type=AIComponentType.RAG_PIPELINE)]
        result = a.assess_rag_pipeline(cfgs)
        # Missing all services
        assert len(result.risks) > 0

    def test_health_score_bounded(self):
        a = _analyzer()
        result = a.assess_rag_pipeline(_rag_configs())
        assert 0 <= result.overall_health_score <= 100

    def test_all_reliabilities_bounded(self):
        a = _analyzer()
        result = a.assess_rag_pipeline(_rag_configs())
        assert 0 <= result.retrieval_reliability <= 1
        assert 0 <= result.generation_reliability <= 1
        assert 0 <= result.embedding_stability <= 1
        assert 0 <= result.context_utilization <= 1


# ===================================================================
# 13. recommend_ai_guardrails tests
# ===================================================================


class TestRecommendAIGuardrails:
    def test_empty_configs(self):
        a = _analyzer()
        result = a.recommend_ai_guardrails([])
        assert result == []

    def test_llm_api_guardrails(self):
        a = _analyzer()
        cfgs = [_default_config(component_type=AIComponentType.LLM_API)]
        result = a.recommend_ai_guardrails(cfgs)
        names = [g.name for g in result]
        assert "Token Rate Limiter" in names
        assert "Output Validator" in names

    def test_embedding_service_guardrail(self):
        a = _analyzer()
        cfgs = [_default_config(component_type=AIComponentType.EMBEDDING_SERVICE)]
        result = a.recommend_ai_guardrails(cfgs)
        names = [g.name for g in result]
        assert "Embedding Drift Monitor" in names

    def test_vector_db_guardrail(self):
        a = _analyzer()
        cfgs = [_default_config(component_type=AIComponentType.VECTOR_DB)]
        result = a.recommend_ai_guardrails(cfgs)
        names = [g.name for g in result]
        assert "Index Health Check" in names

    def test_rag_pipeline_guardrail(self):
        a = _analyzer()
        cfgs = [_default_config(component_type=AIComponentType.RAG_PIPELINE)]
        result = a.recommend_ai_guardrails(cfgs)
        names = [g.name for g in result]
        assert "Retrieval Quality Gate" in names

    def test_ai_agent_guardrail(self):
        a = _analyzer()
        cfgs = [_default_config(component_type=AIComponentType.AI_AGENT)]
        result = a.recommend_ai_guardrails(cfgs)
        names = [g.name for g in result]
        assert "Action Sandbox" in names

    def test_inference_gateway_guardrail(self):
        a = _analyzer()
        cfgs = [_default_config(component_type=AIComponentType.INFERENCE_GATEWAY)]
        result = a.recommend_ai_guardrails(cfgs)
        names = [g.name for g in result]
        assert "Request Throttle" in names

    def test_prompt_cache_guardrail(self):
        a = _analyzer()
        cfgs = [_default_config(component_type=AIComponentType.PROMPT_CACHE)]
        result = a.recommend_ai_guardrails(cfgs)
        names = [g.name for g in result]
        assert "Cache Invalidation Policy" in names

    def test_model_registry_guardrail(self):
        a = _analyzer()
        cfgs = [_default_config(component_type=AIComponentType.MODEL_REGISTRY)]
        result = a.recommend_ai_guardrails(cfgs)
        names = [g.name for g in result]
        assert "Version Pinning" in names

    def test_feature_store_guardrail(self):
        a = _analyzer()
        cfgs = [_default_config(component_type=AIComponentType.FEATURE_STORE)]
        result = a.recommend_ai_guardrails(cfgs)
        names = [g.name for g in result]
        assert "Feature Freshness Monitor" in names

    def test_training_pipeline_guardrail(self):
        a = _analyzer()
        cfgs = [_default_config(component_type=AIComponentType.TRAINING_PIPELINE)]
        result = a.recommend_ai_guardrails(cfgs)
        names = [g.name for g in result]
        assert "Training Data Validator" in names

    @pytest.mark.parametrize("ctype", list(AIComponentType))
    def test_every_component_type_has_guardrail(self, ctype):
        a = _analyzer()
        cfgs = [_default_config(component_type=ctype)]
        result = a.recommend_ai_guardrails(cfgs)
        assert len(result) >= 1

    def test_deduplicate_same_type(self):
        a = _analyzer()
        cfgs = [
            _default_config(component_type=AIComponentType.LLM_API, model_name="a"),
            _default_config(component_type=AIComponentType.LLM_API, model_name="b"),
        ]
        result = a.recommend_ai_guardrails(cfgs)
        llm_guardrails = [g for g in result if g.target_component_type == AIComponentType.LLM_API]
        assert len(llm_guardrails) == 2  # Token Rate Limiter + Output Validator

    def test_multiple_types(self):
        a = _analyzer()
        cfgs = _rag_configs()
        result = a.recommend_ai_guardrails(cfgs)
        types_covered = {g.target_component_type for g in result}
        assert AIComponentType.LLM_API in types_covered
        assert AIComponentType.EMBEDDING_SERVICE in types_covered
        assert AIComponentType.VECTOR_DB in types_covered
        assert AIComponentType.RAG_PIPELINE in types_covered

    def test_guardrail_priorities(self):
        a = _analyzer()
        cfgs = [
            _default_config(component_type=AIComponentType.LLM_API),
            _default_config(component_type=AIComponentType.AI_AGENT),
            _default_config(component_type=AIComponentType.TRAINING_PIPELINE),
        ]
        result = a.recommend_ai_guardrails(cfgs)
        critical = [g for g in result if g.priority == "critical"]
        assert len(critical) >= 2  # Output Validator + Action Sandbox + Training Data Validator


# ===================================================================
# 14. generate_report tests
# ===================================================================


class TestGenerateReport:
    def test_empty_inputs(self):
        a = _analyzer()
        rpt = a.generate_report([], [])
        assert rpt.total_components == 0
        assert rpt.total_scenarios == 0
        assert rpt.overall_resilience_score == 0.0
        assert rpt.summary != ""

    def test_configs_no_scenarios(self):
        a = _analyzer()
        rpt = a.generate_report([_default_config()], [])
        assert rpt.total_components == 1
        assert rpt.total_scenarios == 0
        assert rpt.overall_resilience_score == 100.0

    def test_single_scenario(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=0.5)
        rpt = a.generate_report([_default_config()], [s])
        assert rpt.total_components == 1
        assert rpt.total_scenarios == 1
        assert len(rpt.scenario_results) == 1
        assert rpt.overall_resilience_score > 0

    def test_multiple_scenarios(self):
        a = _analyzer()
        scenarios = [
            AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=0.5),
            AIResilienceScenario(failure_mode=AIFailureMode.TOKEN_RATE_LIMIT, severity=0.3),
            AIResilienceScenario(failure_mode=AIFailureMode.PROMPT_INJECTION, severity=0.8),
        ]
        rpt = a.generate_report([_default_config()], scenarios)
        assert rpt.total_scenarios == 3
        assert len(rpt.scenario_results) == 3

    def test_report_has_guardrails(self):
        a = _analyzer()
        cfgs = _rag_configs()
        s = AIResilienceScenario(failure_mode=AIFailureMode.MODEL_TIMEOUT, severity=0.5)
        rpt = a.generate_report(cfgs, [s])
        assert len(rpt.guardrails) > 0

    def test_report_summary_contains_counts(self):
        a = _analyzer()
        cfgs = [_default_config(), _default_config(component_type=AIComponentType.VECTOR_DB)]
        scenarios = [
            AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=0.5),
        ]
        rpt = a.generate_report(cfgs, scenarios)
        assert "2" in rpt.summary  # 2 components
        assert "1" in rpt.summary  # 1 scenario

    def test_report_summary_contains_degraded(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=0.5)
        rpt = a.generate_report([_default_config()], [s])
        assert "Degraded" in rpt.summary or "inference_unavailable" in rpt.summary

    def test_report_overall_score_bounded(self):
        a = _analyzer()
        scenarios = [
            AIResilienceScenario(failure_mode=m, severity=1.0) for m in AIFailureMode
        ]
        rpt = a.generate_report([_default_config()], scenarios)
        assert 0 <= rpt.overall_resilience_score <= 100

    def test_report_resilience_score_reflects_severity(self):
        a = _analyzer()
        low = a.generate_report(
            [_default_config()],
            [AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=0.1)],
        )
        high = a.generate_report(
            [_default_config()],
            [AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=1.0)],
        )
        assert low.overall_resilience_score >= high.overall_resilience_score

    def test_report_with_all_failure_modes(self):
        a = _analyzer()
        cfgs = _rag_configs()
        scenarios = [
            AIResilienceScenario(failure_mode=m, severity=0.5) for m in AIFailureMode
        ]
        rpt = a.generate_report(cfgs, scenarios)
        assert rpt.total_scenarios == 10
        assert len(rpt.scenario_results) == 10
        assert rpt.overall_resilience_score >= 0


# ===================================================================
# 15. Edge case & integration tests
# ===================================================================


class TestEdgeCases:
    def test_severity_zero_all_modes(self):
        a = _analyzer()
        for mode in AIFailureMode:
            s = AIResilienceScenario(failure_mode=mode, severity=0.0)
            r = a.simulate_failure(s, [_default_config()])
            assert r.impact_score == 0.0

    def test_severity_one_all_modes(self):
        a = _analyzer()
        for mode in AIFailureMode:
            s = AIResilienceScenario(failure_mode=mode, severity=1.0)
            r = a.simulate_failure(s, [_default_config()])
            assert r.impact_score > 0

    def test_many_replicas(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.MODEL_TIMEOUT, severity=0.9)
        r = a.simulate_failure(s, [_default_config(replicas=100)])
        assert r.impact_score < 50

    def test_component_types_are_str_enum(self):
        for ct in AIComponentType:
            assert isinstance(ct, str)
            assert isinstance(ct.value, str)

    def test_failure_modes_are_str_enum(self):
        for fm in AIFailureMode:
            assert isinstance(fm, str)
            assert isinstance(fm.value, str)

    def test_scenario_custom_duration(self):
        s = AIResilienceScenario(
            failure_mode=AIFailureMode.COLD_START_LATENCY,
            duration_seconds=3600,
        )
        assert s.duration_seconds == 3600

    def test_config_all_component_types(self):
        for ct in AIComponentType:
            cfg = AIComponentConfig(component_type=ct)
            assert cfg.component_type == ct

    def test_guardrail_no_description(self):
        g = AIGuardrail(
            name="n", description="", target_component_type=AIComponentType.LLM_API
        )
        assert g.description == ""

    def test_analyze_then_simulate_consistency(self):
        a = _analyzer()
        cfg = _default_config(replicas=1, fallback_model="")
        analysis = a.analyze_component(cfg)
        s = AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=0.5)
        sim = a.simulate_failure(s, [cfg])
        # Both should report non-trivial impact for a single-replica no-fallback config
        assert analysis.impact_score > 0
        assert sim.impact_score > 0

    def test_rag_assessment_with_extra_components(self):
        a = _analyzer()
        cfgs = _rag_configs()
        cfgs.append(AIComponentConfig(component_type=AIComponentType.AI_AGENT))
        cfgs.append(AIComponentConfig(component_type=AIComponentType.FEATURE_STORE))
        result = a.assess_rag_pipeline(cfgs)
        # Extra components don't break the RAG assessment
        assert result.overall_health_score > 0

    def test_report_empty_configs_with_scenarios(self):
        a = _analyzer()
        s = AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=0.5)
        rpt = a.generate_report([], [s])
        assert rpt.total_components == 0
        assert rpt.total_scenarios == 1
        # Empty configs -> simulate_failure returns default result
        assert len(rpt.scenario_results) == 1

    def test_missing_fallback_model_flag(self):
        a = _analyzer()
        cfg = _default_config(fallback_model="")
        result = a.analyze_component(cfg)
        assert "no_fallback" in result.degraded_capabilities

    def test_report_summary_includes_resilience_score(self):
        a = _analyzer()
        rpt = a.generate_report(
            [_default_config()],
            [AIResilienceScenario(failure_mode=AIFailureMode.GPU_OOM, severity=0.5)],
        )
        assert "resilience score" in rpt.summary.lower()

    def test_failure_base_impact_all_modes_covered(self):
        from faultray.simulator.ai_infra_resilience import _FAILURE_BASE_IMPACT
        for mode in AIFailureMode:
            assert mode in _FAILURE_BASE_IMPACT
