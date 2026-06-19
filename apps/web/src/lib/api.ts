// SEC (U28): validate API_BASE and lock token attachment to a trusted origin.
//
// NEXT_PUBLIC_FAULTRAY_API_URL selects the backend origin. Because we attach the
// Supabase access token (`Authorization: Bearer ...`) to these requests, an
// attacker-controlled or misconfigured base URL would exfiltrate the token and
// request bodies (SSRF / token leak). We therefore (1) require the configured
// base to be a valid absolute https:// URL (http:// only for localhost in dev),
// and (2) only build requests against that validated origin with a relative
// path. A malformed/insecure non-empty base fails CLOSED (throws at module
// load) rather than silently leaking credentials.
//
// A legacy `NEXT_PUBLIC_API_URL` is still honored as a fallback through the
// rename rollout; new code should set only NEXT_PUBLIC_FAULTRAY_API_URL.
const _RAW_API_BASE = (
  process.env.NEXT_PUBLIC_FAULTRAY_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  ""
).trim();

function _isLocalhost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]" || hostname === "::1";
}

/**
 * Validated, trusted backend origin. "" means same-origin (relative fetch).
 * Throws on a malformed/insecure configured base so deploys fail closed
 * instead of attaching the access token to an untrusted host.
 */
export const TRUSTED_API_ORIGIN: string = (() => {
  if (!_RAW_API_BASE) return "";
  let u: URL;
  try {
    u = new URL(_RAW_API_BASE);
  } catch {
    throw new Error("[API] NEXT_PUBLIC_FAULTRAY_API_URL must be a valid absolute URL");
  }
  if (u.protocol !== "https:" && !(u.protocol === "http:" && _isLocalhost(u.hostname))) {
    throw new Error("[API] NEXT_PUBLIC_FAULTRAY_API_URL must use https:// (http:// only for localhost)");
  }
  return u.origin;
})();

// Validated prefix for building request URLs ("" = relative/same-origin).
const API_BASE = TRUSTED_API_ORIGIN ? _RAW_API_BASE.replace(/\/+$/, "") : "";

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

// SEC (U28): never store the raw access token in cache keys, and key by a
// per-token fingerprint so one user's cached response can't be served to
// another (cross-user cache poisoning). FNV-1a 32-bit, non-reversible.
function _fingerprint(s: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(36);
}

function _cacheKey(path: string, token?: string): string {
  return `${token ? _fingerprint(token) : "anon"}:${path}`;
}

// FETCHPAT-01: Default timeout 30s to prevent indefinite hangs
const DEFAULT_TIMEOUT_MS = 30_000;

// ERROR-03: Retry logic with exponential backoff for transient errors
const RETRY_STATUS_CODES = new Set([429, 500, 502, 503, 504]);
const MAX_RETRIES = 3;

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Resolve the current Supabase access token for authenticating tenant-scoped
 * API calls. No-op (undefined) on the server or when Supabase is unconfigured;
 * the backend then treats the request as demo/unauthenticated.
 */
async function _authToken(): Promise<string | undefined> {
  if (typeof window === "undefined") return undefined;
  try {
    const { getAccessToken } = await import("@/lib/supabase/client");
    return await getAccessToken();
  } catch {
    return undefined;
  }
}

// SEC (U28): only retry idempotent methods. Retrying POST/PATCH/PUT/DELETE on
// 429/5xx/network errors can duplicate side effects (double checkout, double
// save, repeated destructive mutations).
const IDEMPOTENT_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { method = "GET", body, token, signal, cacheTtl } = options;
  const isIdempotent = IDEMPOTENT_METHODS.has(method.toUpperCase());

  // SEC (U28): reject absolute / protocol-relative paths so the `path` arg
  // cannot redirect a token-bearing request to an arbitrary host.
  if (!path.startsWith("/") || path.startsWith("//")) {
    throw new Error("[API] path must be a relative path starting with '/'");
  }

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
  // Track listeners so they can be removed on every exit path (avoid leaking a
  // retained closure on a long-lived/shared caller signal).
  let abort: (() => void) | undefined;
  let mergeController: AbortController | undefined;
  if (signal) {
    // Merge: abort if either fires
    mergeController = new AbortController();
    abort = () => mergeController!.abort();
    signal.addEventListener("abort", abort, { once: true });
    timeoutController.signal.addEventListener("abort", abort, { once: true });
    combinedSignal = mergeController.signal;
    // If the caller signal already fired before we attached the listener, the
    // abort event won't replay — propagate the cancellation explicitly.
    if (signal.aborted) mergeController.abort();
  } else {
    combinedSignal = timeoutController.signal;
  }

  // Remove abort listeners and clear the timeout. Safe to call multiple times.
  const cleanup = () => {
    clearTimeout(timeoutId);
    if (signal && abort) {
      signal.removeEventListener("abort", abort);
      timeoutController.signal.removeEventListener("abort", abort);
    }
  };

  // ERROR-03: Retry loop with exponential backoff
  let lastError: Error = new Error("API request failed");
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    // Abort if caller signal is already aborted (or aborted during a backoff
    // sleep): surface a proper AbortError rather than a stale/generic error.
    if (combinedSignal.aborted) {
      cleanup();
      throw new DOMException("Aborted", "AbortError");
    }

    try {
      // FETCH-01 fix: pass AbortSignal when provided to prevent memory leaks
      const res = await fetch(`${API_BASE}${path}`, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
        signal: combinedSignal,
      });

      if (!res.ok) {
        // ERROR-03: Retry on transient server errors — idempotent methods only.
        if (RETRY_STATUS_CODES.has(res.status) && isIdempotent && attempt < MAX_RETRIES) {
          const delay = Math.min(1000 * 2 ** attempt, 8000);
          await sleep(delay);
          lastError = new Error(`HTTP ${res.status}: ${res.statusText}`);
          continue;
        }
        const error = await res.json().catch(() => ({ message: res.statusText }));
        throw new Error(error.error?.message || error.message || "API request failed");
      }

      // A successful empty-body response (e.g. 204 No Content) has no JSON to
      // parse; res.json() would throw and trigger a needless retry of an
      // already-successful idempotent request.
      const data =
        res.status === 204
          ? (undefined as T)
          : ((await res.json()) as T);

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

      cleanup();
      return data;
    } catch (err) {
      // Don't retry on abort (user-initiated or timeout)
      if (err instanceof Error && err.name === "AbortError") {
        cleanup();
        throw err;
      }
      lastError = err instanceof Error ? err : new Error(String(err));
      // SEC (U28): never retry non-idempotent methods on network errors.
      if (!isIdempotent) {
        cleanup();
        throw lastError;
      }
      if (attempt < MAX_RETRIES) {
        const delay = Math.min(1000 * 2 ** attempt, 8000);
        await sleep(delay);
      }
    }
  }
  cleanup();
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
    apiFetch<BenchmarkData>(`/api/finance?action=benchmark&industry=${encodeURIComponent(industry)}`, { token }),

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
      `/api/apm/agents/${encodeURIComponent(agentId)}/metrics${metric ? `?metric_name=${encodeURIComponent(metric)}` : ""}`,
      { token }
    ),

  getApmAlerts: (severity?: string, token?: string) =>
    apiFetch<ApmAlert[]>(
      `/api/apm/alerts${severity ? `?severity=${encodeURIComponent(severity)}` : ""}`,
      { token }
    ),

  getApmStats: (token?: string) =>
    apiFetch<ApmStats>("/api/apm/stats", { token }),

  // Projects are tenant-scoped: the Python /api/projects endpoint authenticates
  // the caller via their Supabase access token and filters by team. When a
  // token is not passed explicitly we resolve it from the browser session, so
  // every client call is authenticated without each call site wiring it up.
  getProjects: async (token?: string) =>
    apiFetch<Project[]>("/api/projects", { token: token ?? (await _authToken()) }),

  getProject: async (id: string, token?: string) =>
    apiFetch<ProjectWithRuns>(`/api/projects?id=${encodeURIComponent(id)}`, { token: token ?? (await _authToken()) }),

  createProject: async (
    data: { name: string; description: string; topology_yaml?: string; topology_type?: string },
    token?: string,
  ) =>
    apiFetch<Project>("/api/projects", { method: "POST", body: data, token: token ?? (await _authToken()) }),

  updateProject: async (id: string, data: Partial<Project>, token?: string) =>
    apiFetch<Project>(`/api/projects?id=${encodeURIComponent(id)}`, { method: "PATCH", body: data, token: token ?? (await _authToken()) }),

  deleteProject: async (id: string, token?: string) =>
    apiFetch<{ ok: boolean; id: string }>(`/api/projects?id=${encodeURIComponent(id)}`, { method: "DELETE", token: token ?? (await _authToken()) }),

  getProjectRuns: async (projectId: string, token?: string) =>
    apiFetch<ProjectWithRuns>(`/api/projects?id=${encodeURIComponent(projectId)}`, { token: token ?? (await _authToken()) }),

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
