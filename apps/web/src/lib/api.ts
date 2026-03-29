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

export const api = {
  simulate: (data: { topology?: string; topology_yaml?: string; sample?: string }, token?: string) =>
    apiFetch<SimulationResult>("/api/simulate", {
      method: "POST",
      body: data,
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
};
