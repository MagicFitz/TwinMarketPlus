export type RunStatus = "draft" | "queued" | "running" | "stopping" | "completed" | "failed" | "cancelled";
export type HealthStatus = "healthy" | "degraded" | "stale" | "unavailable";
export type StageStatus = "pending" | "running" | "completed" | "failed" | "retrying" | "skipped";

export interface RunConfig {
  market_snapshot_id?: string | null;
  market_data_mode?: "legacy" | "snapshot";
  allow_missing_news?: boolean;
  user_count: number;
  start_date: string;
  end_date: string;
  max_workers: number;
  activate_prob: number;
  prob_of_technical: number;
  random_seed: number;
  template_db?: string;
  belief_source?: string;
  config_path?: string;
}

export interface Run {
  run_id: string;
  name: string;
  description: string;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  status: RunStatus;
  health: HealthStatus;
  config: RunConfig;
  output_dir: string;
  checkpoint: { last_completed_date: string | null; next_date: string | null };
  pid: number | null;
  exit_code: number | null;
  failure_reason: string | null;
  last_heartbeat: string | null;
  last_event_id: number;
  archived: boolean;
}

export interface RunList { items: Run[]; page: number; page_size: number; total: number }
export interface RunCreate { name: string; description?: string; run_id?: string; config: RunConfig }

export interface StageSnapshot {
  status: StageStatus;
  substage?: string | null;
  duration_ms?: number | null;
  attempt?: number;
  message?: string | null;
  input_summary?: Record<string, unknown>;
  output_summary?: Record<string, unknown>;
  updated_at?: string | null;
}

export interface AgentSnapshot {
  agent_id: string;
  worker_id?: string | null;
  last_stage?: string;
  updated_at?: string;
  stages: Record<string, StageSnapshot>;
}

export interface WorkerSnapshot extends StageSnapshot {
  worker_id: string;
  agent_id: string;
  stage: string;
}

export interface RuntimeEvent {
  event_id: number;
  run_id: string;
  event: "stage_started" | "stage_completed" | "stage_skipped" | "stage_failed" | "stage_retrying";
  scope: "run" | "day" | "agent" | "market" | "social" | "artifact" | "system";
  stage: string;
  substage?: string | null;
  simulation_date?: string | null;
  agent_id?: string | null;
  worker_id?: string | null;
  message?: string | null;
  error_code?: string | null;
  duration_ms?: number | null;
  attempt?: number;
  started_at?: string;
  ended_at?: string | null;
  input_summary?: Record<string, unknown>;
  output_summary?: Record<string, unknown>;
}

export interface RuntimeSnapshot {
  run_id: string;
  last_event_id: number;
  lifecycle: RunStatus;
  health: HealthStatus;
  run: StageSnapshot & { health?: HealthStatus };
  day: { date: string | null; stages: Record<string, StageSnapshot> };
  agents: AgentSnapshot[];
  workers: WorkerSnapshot[];
  agent_counts: Record<StageStatus, number>;
  today_summary: Record<string, number>;
  diagnostics: RuntimeEvent[];
}

export interface PagedResult<T = Record<string, unknown>> {
  items: T[];
  page?: number;
  page_size?: number;
  total?: number;
  source?: string;
  updated_at?: string;
}

export interface AgentMember extends Record<string, unknown> {
  user_id: string;
  user_type?: string;
  location?: string;
  current_cash?: number;
  total_value?: number;
  return_rate?: number;
}

export interface MarketData {
  assets: Array<{ stock_id: string; name: string; industry: string; weight: number; description?: string }>;
  selected: string;
  prices: Array<{ date: string; close_price: number; pct_chg: number; vol: number }>;
  source: string;
}

export interface DocumentItem { path: string; title: string; category: string; order: number; content?: string }
export interface DocumentList { items: DocumentItem[] }

export interface LanguageModelSettings {
  kind: "language";
  configured: boolean;
  api_type: string;
  provider: string;
  model_name: string;
  base_url: string;
  timeout: number | null;
  api_key_configured: boolean;
}

export interface EmbeddingModelSettings {
  kind: "embedding";
  configured: boolean;
  provider: string;
  model_name: string;
  base_url: string;
  endpoint: string;
  timeout: number | null;
  max_retries: number | null;
  api_key_configured: boolean;
}

export interface ModelSettings { language: LanguageModelSettings; embedding: EmbeddingModelSettings }
export interface LanguageModelUpdate {
  api_type: string;
  provider: string;
  model_name: string;
  base_url: string;
  timeout: number | null;
  api_key?: string;
}
export interface EmbeddingModelUpdate {
  provider: string;
  model_name: string;
  base_url: string;
  endpoint: string;
  timeout: number | null;
  max_retries: number | null;
  api_key?: string;
}
