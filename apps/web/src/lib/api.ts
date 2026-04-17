// LIB-01 fix: validate API_BASE is defined when set to a non-empty value.
//
// Env var name aligns with .env.local (`NEXT_PUBLIC_FAULTRAY_API_URL`).
// A legacy `NEXT_PUBLIC_API_URL` is still honored as a fallback so existing
// deploys and CI envs keep working through the rename rollout; new code
// should set only NEXT_PUBLIC_FAULTRAY_API_URL.
const API_BASE =
  process.env.NEXT_PUBLIC_FAULTRAY_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "";

interface ApiOptions {
  method?: string;
  body?: unknown;
  token?: string;
  signal?: AbortSignal;
  /** FETCHPAT-05: TTL in ms for GET request caching. 0 = no cache (default) */
  cacheTtl?: number;
}

// FETCHPAT-05: In-memory GET cache (page-level deduplication)
interface CacheEntry { data: unknown; expiresAt: number; }
const _apiCache = new Map<string, CacheEntry>();

function _cacheKey(path: string, token?: string): string {
  return `${token ?? "anon"}:${path}`;
}

// FETCHPAT-01: Default timeout 30s to prevent indefinite hangs
const DEFAULT_TIMEOUT_MS = 30_000;

// ERROR-03: Retry logic with exponential backoff for transient errors
const RETRY_STATUS_CODES = new Set([429, 500, 502, 503, 504]);
const MAX_RETRIES = 3;

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { method = "GET", body, token, signal, cacheTtl } = options;

  // FETCHPAT-05: Serve from cache for GET requests with cacheTtl set
  if (method === "GET" && cacheTtl && cacheTtl > 0) {
    const key = _cacheKey(path, token);
    const entry = _apiCache.get(key);
    if (entry && entry.expiresAt > Date.now()) {
      return entry.data as T;
    }
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  // FETCHPAT-01: Combine caller signal with internal timeout signal
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => timeoutController.abort(), DEFAULT_TIMEOUT_MS);
  let combinedSignal: AbortSignal;
  if (signal) {
    // Merge: abort if either fires
    const mergeController = new AbortController();
    const abort = () => mergeController.abort();
    signal.addEventListener("abort", abort, { once: true });
    timeoutController.signal.addEventListener("abort", abort, { once: true });
    combinedSignal = mergeController.signal;
  } else {
    combinedSignal = timeoutController.signal;
  }

  // ERROR-03: Retry loop with exponential backoff
  let lastError: Error = new Error("API request failed");
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    // Abort if caller signal is already aborted
    if (combinedSignal.aborted) break;

    try {
      // FETCH-01 fix: pass AbortSignal when provided to prevent memory leaks
      const res = await fetch(`${API_BASE}${path}`, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
        signal: combinedSignal,
      });

      if (!res.ok) {
        // ERROR-03: Retry on transient server errors
        if (RETRY_STATUS_CODES.has(res.status) && attempt < MAX_RETRIES) {
          const delay = Math.min(1000 * 2 ** attempt, 8000);
          await sleep(delay);
          lastError = new Error(`HTTP ${res.status}: ${res.statusText}`);
          continue;
        }
        const error = await res.json().catch(() => ({ message: res.statusText }));
        throw new Error(error.error?.message || error.message || "API request failed");
      }

      const data = await res.json() as T;

      // FETCHPAT-05: Store in cache for GET requests with cacheTtl
      if (method === "GET" && cacheTtl && cacheTtl > 0) {
        _apiCache.set(_cacheKey(path, token), { data, expiresAt: Date.now() + cacheTtl });
        // Evict stale entries periodically to avoid unbounded growth
        if (_apiCache.size > 100) {
          const now = Date.now();
          for (const [k, v] of _apiCache) {
            if (v.expiresAt < now) _apiCache.delete(k);
          }
        }
      }

      clearTimeout(timeoutId);
      return data;
    } catch (err) {
      // Don't retry on abort (user-initiated or timeout)
      if (err instanceof Error && err.name === "AbortError") {
        clearTimeout(timeoutId);
        throw err;
      }
      lastError = err instanceof Error ? err : new Error(String(err));
      if (attempt < MAX_RETRIES) {
        const delay = Math.min(1000 * 2 ** attempt, 8000);
        await sleep(delay);
      }
    }
  }
  clearTimeout(timeoutId);
  throw lastError;
}

// FETCHPAT-06: 軽量なランタイム型ガード
// null/undefined・期待するフィールドの欠如を検出してクラッシュを防ぐ
function assertObject(value: unknown, context: string): asserts value is Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`[API] Expected object at ${context}, got ${typeof value}`);
  }
}

function assertArray(value: unknown, context: string): asserts value is unknown[] {
  if (!Array.isArray(value)) {
    throw new Error(`[API] Expected array at ${context}, got ${typeof value}`);
  }
}

/** 重要なシミュレーションレスポンスの最低限のフィールドを検証 */
function validateSimulationResult(raw: unknown): void {
  assertObject(raw, "SimulationResult");
  if (typeof raw.overall_score !== "number") {
    throw new Error("[API] SimulationResult.overall_score is missing or not a number");
  }
  if (typeof raw.availability_estimate !== "string") {
    throw new Error("[API] SimulationResult.availability_estimate is missing or not a string");
  }
  if (!Array.isArray(raw.critical_failures)) {
    throw new Error("[API] SimulationResult.critical_failures is missing or not an array");
  }
}

export { assertObject, assertArray, validateSimulationResult };

export interface CalcFactor {
  name: string;
  effect: string;
  detail: string;
}

export interface CalcLayer {
  name: string;
  nines: number;
  max_possible: number;
  factors: CalcFactor[];
}

export interface CalculationEvidence {
  layers: CalcLayer[];
  bottleneck: string;
  formula: string;
}

export interface CascadeTimelineEvent {
  time: string;
  event: string;
  component: string;
  type: "trigger" | "degradation" | "failure" | "cascade" | "outage" | "recovery";
}

export interface CascadeSimulation {
  id: string;
  trigger: string;
  severity: string;
  affected_components: number;
  total_components: number;
  blast_radius_percent: number;
  estimated_recovery_minutes: number;
  timeline: CascadeTimelineEvent[];
}

export interface SimulationScenario {
  id: number;
  name: string;
  result: "PASSED" | "WARNING" | "CRITICAL";
  risk_score: number;
  affected: string[];
}

export interface SimulationLog {
  total_scenarios: number;
  passed: number;
  critical: number;
  warning: number;
  duration_ms: number;
  scenarios: SimulationScenario[];
}

export interface SimulationResult {
  overall_score: number;
  availability_estimate: string;
  nines: number;
  scenarios_passed: number;
  scenarios_failed: number;
  total_scenarios: number;
  layers?: {
    software: number;
    hardware: number;
    theoretical: number;
    operational?: number;
    external?: number;
  };
  critical_failures: Array<{
    scenario: string;
    impact: string;
    severity: string;
  }>;
  suggestions: Array<{
    title: string;
    description: string;
    impact: string;
    effort: string;
  }>;
  calculation_evidence?: CalculationEvidence;
  cascade_simulations?: CascadeSimulation[];
  simulation_log?: SimulationLog;
}

export interface SimulationRun {
  id: number;
  created_at: string;
  overall_score: number;
  availability_estimate: string;
  engine_type: string;
  scenarios_passed: number;
  scenarios_failed: number;
  total_scenarios: number;
}

export interface ScanSummary {
  region?: string;
  components_found: number;
  dependencies_inferred: number;
  scan_duration_seconds?: number;
  warnings?: string[];
  namespace?: string | null;
}

export interface CloudSimulationResult extends SimulationResult {
  scan_summary: ScanSummary;
}

export interface HeatmapComponent {
  id: string;
  name: string;
  type: string;
  risk_score: number;
  category: string;
}

export interface HeatmapData {
  components: HeatmapComponent[];
  categories: string[];
  max_risk: number;
}

export interface WhatIfResult {
  baseline: { overall_score: number; availability_estimate: string; nines: number };
  modified: { overall_score: number; nines: number };
  delta: { score: number; direction: string };
  component_id: string;
  parameter: string;
  original_value: number;
  new_value: number;
  available_parameters: string[];
}

export interface ScoreLayer {
  name: string;
  score: number;
  weight: number;
  weighted_score: number;
  factors: Array<{ name: string; score: number; impact: string }>;
}

export interface ScoreExplainData {
  overall_score: number;
  layers: ScoreLayer[];
  top_detractors: Array<{ factor: string; layer: string; score: number; potential_gain: number }>;
}

export interface CostAnalysis {
  current: { nines: number; downtime_hours_per_year: number; annual_cost: number };
  target: { nines: number; downtime_hours_per_year: number; annual_cost: number };
  potential_savings: number;
  revenue_per_hour: number;
  industry: string;
  improvements: Array<{
    action: string;
    cost: number;
    score_gain: number;
    nines_gain: number;
    annual_savings: number;
    roi_percent: number;
    payback_days: number;
  }>;
}

export interface AttackSurfaceData {
  summary: {
    total_components: number;
    external_facing: number;
    internal_only: number;
    risk_level: string;
    attack_vectors: number;
  };
  external_components: Array<{
    id: string;
    name: string;
    exposure: string;
    ports: number[];
    protocols: string[];
    risk_score: number;
    vulnerabilities: Array<{ type: string; severity: string; mitigation: string }>;
  }>;
  internal_components: Array<{ id: string; name: string; risk_score: number }>;
  recommendations: string[];
}

export interface FmeaData {
  analysis_date: string;
  total_failure_modes: number;
  critical_rpn_threshold: number;
  high_rpn_count: number;
  failure_modes: Array<{
    id: string;
    component: string;
    failure_mode: string;
    effect: string;
    severity: number;
    occurrence: number;
    detection: number;
    rpn: number;
    recommended_action: string;
    status: string;
  }>;
  rpn_distribution: { critical: number; high: number; medium: number; low: number };
}

export interface ChatResponse {
  response: string;
  sources: string[];
  suggested_actions: Array<{ label: string; href: string }>;
}

export interface ExecutiveReport {
  title: string;
  generated_at: string;
  executive_summary: {
    overall_score: number;
    availability_estimate: string;
    risk_level: string;
    total_components: number;
    total_scenarios_tested: number;
    critical_issues: number;
    recommendations_count: number;
  };
  key_findings: Array<{
    severity: string;
    finding: string;
    impact: string;
    recommendation: string;
  }>;
  availability_breakdown: {
    hardware_nines: number;
    software_nines: number;
    theoretical_nines: number;
    bottleneck: string;
  };
  compliance_status: Record<string, { status: string; score: number }>;
  improvement_roadmap: Array<{
    priority: number;
    action: string;
    effort: string;
    impact: string;
    timeline: string;
  }>;
}

export interface IncidentTimeline {
  time: string;
  event: string;
  component: string;
  type: string;
}

export interface Incident {
  id: string;
  title: string;
  severity: string;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  affected_components: string[];
  root_cause: string;
  timeline: IncidentTimeline[];
}

export interface IncidentsData {
  incidents: Incident[];
  summary: {
    total_incidents: number;
    critical: number;
    high: number;
    medium: number;
    average_duration_minutes: number;
    most_affected_component: string;
  };
}

export interface BenchmarkCategory {
  name: string;
  your_score: number;
  industry_avg: number;
  top_10: number;
}

export interface BenchmarkData {
  industry: string;
  industry_id: string;
  your_score: number;
  industry_average: number;
  industry_top_10: number;
  industry_bottom_10: number;
  percentile: number;
  categories: BenchmarkCategory[];
  regulatory_requirements: string[];
  typical_sla: string;
}

export interface ApmAgent {
  agent_id: string;
  hostname: string;
  ip_address: string;
  status: string;
  os_info: string;
  last_seen: string;
  cpu_percent?: number;
  memory_percent?: number;
  disk_percent?: number;
}

export interface ApmMetricPoint {
  metric_name: string;
  value: number;
  sample_count: number;
  bucket_epoch: number;
}

export interface ApmAlert {
  id: string;
  severity: string;
  rule_name: string;
  agent_id: string;
  metric_name: string;
  metric_value: number;
  threshold: number;
  fired_at: string;
}

export interface ApmStats {
  total_agents: number;
  active_agents: number;
  total_metrics: number;
  total_alerts: number;
  db_size_mb: number;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  topology_yaml: string | null;
  topology_type?: string;
  status?: string;
  created_at: string;
  updated_at: string;
  // Computed from simulation_runs
  last_score?: number | null;
  last_run_at?: string | null;
  run_count?: number;
}

export interface ProjectWithRuns extends Project {
  runs: Array<SimulationRun & {
    critical_failures?: Array<{ scenario: string; impact: string; severity: string }>;
    suggestions?: Array<{ title: string; description: string; impact: string; effort: string }>;
  }>;
}

export const api = {
  simulate: async (data: { topology?: string; topology_yaml?: string; sample?: string }, token?: string): Promise<SimulationResult> => {
    const result = await apiFetch<SimulationResult>("/api/simulate", {
      method: "POST",
      body: data,
      token,
    });
    // FETCHPAT-06: ランタイム型検証 — 予期しない構造でのクラッシュを防止
    validateSimulationResult(result);
    return result;
  },

  scanCloud: (
    data: {
      action: "aws" | "gcp" | "azure";
      access_key_id?: string;
      secret_access_key?: string;
      role_arn?: string;
      region?: string;
      credentials_json?: string;
      project_id?: string;
      tenant_id?: string;
      client_id?: string;
      client_secret?: string;
      subscription_id?: string;
    },
    token?: string,
  ) =>
    apiFetch<CloudSimulationResult>("/api/discovery", {
      method: "POST",
      body: data,
      token,
    }),

  parseTerraform: (data: { tfstate_json: string }, token?: string) =>
    apiFetch<CloudSimulationResult>("/api/discovery", {
      method: "POST",
      body: { action: "terraform", ...data },
      token,
    }),

  parseKubernetes: (
    data: { manifests: string; namespace?: string },
    token?: string,
  ) =>
    apiFetch<CloudSimulationResult>("/api/discovery", {
      method: "POST",
      body: { action: "kubernetes", ...data },
      token,
    }),

  // FETCHPAT-05: cacheTtl=30000 (30s) で重複呼び出しをページ内でデデュープ
  getRuns: (token?: string, limit = 50) =>
    apiFetch<{ runs: SimulationRun[] }>(`/api/v1/runs?limit=${limit}`, { token, cacheTtl: 30_000 }),

  getRun: (id: number, token?: string) =>
    apiFetch<SimulationRun & SimulationResult>(`/api/v1/runs/${id}`, { token, cacheTtl: 30_000 }),

  // APIRESP-08: より具体的な型（GraphDataに近い構造）を返す
  getGraphData: (token?: string) =>
    apiFetch<{ nodes?: unknown[]; edges?: unknown[]; [key: string]: unknown }>("/api/v1/graph-data", { token, cacheTtl: 30_000 }),

  getScoreHistory: (token?: string, limit = 30) =>
    apiFetch<{ history: Array<{ date: string; score: number }> }>(
      `/api/v1/score-history?limit=${limit}`,
      { token, cacheTtl: 30_000 }
    ),

  getCompliance: (framework: string, token?: string) =>
    apiFetch<Record<string, unknown>>("/api/compliance", {
      method: "POST",
      body: { framework },
      token,
    }),

  getAnalysis: (token?: string) =>
    apiFetch<Record<string, unknown>>("/api/v1/analyze", { token }),

  // New API methods
  getHeatmap: (topologyYaml?: string, token?: string) =>
    apiFetch<HeatmapData>("/api/analysis", {
      method: "POST",
      body: topologyYaml ? { action: "heatmap", topology_yaml: topologyYaml } : { action: "heatmap" },
      token,
    }),

  whatIf: (componentId: string, parameter: string, value: number, token?: string) =>
    apiFetch<WhatIfResult>("/api/analysis", {
      method: "POST",
      body: { action: "whatif", component_id: componentId, parameter, value },
      token,
    }),

  getScoreExplain: (token?: string) =>
    apiFetch<ScoreExplainData>("/api/analysis?action=score-explain", { token }),

  analyzeCost: (revenuePerHour: number, industry: string, token?: string) =>
    apiFetch<CostAnalysis>("/api/finance", {
      method: "POST",
      body: { action: "cost", revenue_per_hour: revenuePerHour, industry },
      token,
    }),

  getAttackSurface: (token?: string) =>
    apiFetch<AttackSurfaceData>("/api/risk?action=attack-surface", { token }),

  getFmea: (token?: string) =>
    apiFetch<FmeaData>("/api/risk?action=fmea", { token }),

  chat: (message: string, token?: string) =>
    apiFetch<ChatResponse>("/api/chat", {
      method: "POST",
      body: { message },
      token,
    }),

  getExecutiveReport: (format: "json" | "html" = "json", token?: string) =>
    apiFetch<ExecutiveReport>(`/api/reports?action=report&format=${format}`, { token }),

  getIncidents: (token?: string) =>
    apiFetch<IncidentsData>("/api/reports?action=incidents", { token }),

  getBenchmark: (industry: string, token?: string) =>
    apiFetch<BenchmarkData>(`/api/finance?action=benchmark&industry=${industry}`, { token }),

  createCheckoutSession: (plan: "starter" | "pro" | "business", interval: "month" | "year" = "month", token?: string) =>
    apiFetch<{ url: string }>("/api/stripe/checkout", {
      method: "POST",
      body: { plan, interval },
      token,
    }),

  getApmAgents: (token?: string) =>
    apiFetch<ApmAgent[]>("/api/apm/agents", { token }),

  getApmMetrics: (agentId: string, metric?: string, token?: string) =>
    apiFetch<ApmMetricPoint[]>(
      `/api/apm/agents/${agentId}/metrics${metric ? `?metric_name=${metric}` : ""}`,
      { token }
    ),

  getApmAlerts: (severity?: string, token?: string) =>
    apiFetch<ApmAlert[]>(
      `/api/apm/alerts${severity ? `?severity=${severity}` : ""}`,
      { token }
    ),

  getApmStats: (token?: string) =>
    apiFetch<ApmStats>("/api/apm/stats", { token }),

  getProjects: (token?: string) =>
    apiFetch<Project[]>("/api/projects", { token }),

  getProject: (id: string, token?: string) =>
    apiFetch<ProjectWithRuns>(`/api/projects?id=${id}`, { token }),

  createProject: (
    data: { name: string; description: string; topology_yaml?: string; topology_type?: string },
    token?: string,
  ) =>
    apiFetch<Project>("/api/projects", { method: "POST", body: data, token }),

  updateProject: (id: string, data: Partial<Project>, token?: string) =>
    apiFetch<Project>(`/api/projects?id=${id}`, { method: "PATCH", body: data, token }),

  deleteProject: (id: string, token?: string) =>
    apiFetch<{ ok: boolean; id: string }>(`/api/projects?id=${id}`, { method: "DELETE", token }),

  getProjectRuns: (projectId: string, token?: string) =>
    apiFetch<ProjectWithRuns>(`/api/projects?id=${projectId}`, { token }),

  saveRun: (
    data: {
      project_id?: string;
      overall_score: number;
      availability_estimate: string;
      nines?: number;
      engine_type?: string;
      scenarios_passed: number;
      scenarios_failed: number;
      total_scenarios: number;
      result_data?: Record<string, unknown>;
    },
    token?: string,
  ) =>
    apiFetch<{ ok: boolean; id: string }>("/api/simulate", {
      method: "POST",
      body: { action: "save-run", ...data },
      token,
    }),
};
