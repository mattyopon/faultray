/**
 * LIB-04: Shared type definitions for FaultRay SaaS
 *
 * Re-exports all domain types from api.ts for convenient single-import access.
 * Components should import from here rather than directly from api.ts.
 *
 * Usage:
 *   import type { SimulationResult, SimulationRun, Project } from "@/lib/types";
 */

export type {
  CalcFactor,
  CalcLayer,
  CalculationEvidence,
  CascadeTimelineEvent,
  CascadeSimulation,
  SimulationScenario,
  SimulationLog,
  SimulationResult,
  SimulationRun,
  ScanSummary,
  CloudSimulationResult,
  HeatmapComponent,
  HeatmapData,
  WhatIfResult,
  ScoreLayer,
  ScoreExplainData,
  CostAnalysis,
  AttackSurfaceData,
  FmeaData,
  ChatResponse,
  Project,
} from "@/lib/api";

/** Plan tiers for the SaaS billing system */
export type PlanTier = "free" | "pro" | "business";

/** Locale codes supported by FaultRay */
export type Locale = "en" | "ja" | "de" | "fr" | "zh" | "ko" | "es" | "pt";

/** Generic paginated response wrapper */
export interface Paginated<T> {
  data: T[];
  total: number;
  limit: number;
  offset: number;
}

/** Standard API error response shape */
export interface ApiError {
  error: {
    message: string;
    code?: string;
  };
}
