const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

interface ApiOptions {
  method?: string;
  body?: unknown;
  token?: string;
}

async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { method = "GET", body, token } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ message: res.statusText }));
    throw new Error(error.error?.message || error.message || "API request failed");
  }

  return res.json();
}

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
  simulate: (data: { topology?: string; topology_yaml?: string; sample?: string }, token?: string) =>
    apiFetch<SimulationResult>("/api/simulate", {
      method: "POST",
      body: data,
      token,
    }),

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

  getRuns: (token?: string, limit = 50) =>
    apiFetch<{ runs: SimulationRun[] }>(`/api/v1/runs?limit=${limit}`, { token }),

  getRun: (id: number, token?: string) =>
    apiFetch<SimulationRun & SimulationResult>(`/api/v1/runs/${id}`, { token }),

  getGraphData: (token?: string) =>
    apiFetch<Record<string, unknown>>("/api/v1/graph-data", { token }),

  getScoreHistory: (token?: string, limit = 30) =>
    apiFetch<{ history: Array<{ date: string; score: number }> }>(
      `/api/v1/score-history?limit=${limit}`,
      { token }
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

  createCheckoutSession: (plan: "pro" | "business", token?: string) =>
    apiFetch<{ url: string }>("/api/billing", {
      method: "POST",
      body: { plan },
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
