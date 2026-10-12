export interface DataSource {
  source_id: 'tushare';
  provider: 'tushare';
  enabled: boolean;
  token_configured: boolean;
  credential_source: 'environment' | 'local';
  status: 'unconfigured' | 'untested' | 'available' | 'partial' | 'failed';
  last_tested_at: string | null;
  capabilities: Record<string, { status: string; error_code: string | null; message?: string; sample_rows?: number }>;
  deferred_datasets: string[];
}
export interface DataSourceUpdate { token?: string | null; enabled?: boolean }
export type MarketDataset = 'trade_cal' | 'daily' | 'daily_basic';
export interface MarketSyncCreate {
  source_id?: 'tushare'; mode: 'incremental' | 'backfill'; start_date?: string; end_date?: string;
  datasets?: MarketDataset[]; allow_missing_news: boolean;
}
export interface MarketSyncJob {
  job_id: string; request: MarketSyncCreate & { baseline_snapshot_id: string | null };
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'; stage: string; progress: number;
  cancel_requested: boolean; error_code: string | null; error: string | null;
  snapshot_id: string | null; pid: number | null; created_at: string; updated_at: string;
}
export interface MarketSnapshot {
  schema_version: number; snapshot_id: string; provider: string; status: 'ready' | 'ready_with_warnings';
  as_of: string; start_date: string; earliest_run_date: string; effective_through: string; calendar_through: string;
  active?: boolean; created_by_job_id: string; transform_version: string;
  asset_definition_sha256: string; asset_definition_version: number;
  source_range: { start_date: string; end_date: string }; baseline_snapshot_id: string | null;
  units: Record<string, string>; datasets: Record<string, { status: 'available' | 'missing'; through?: string; ranking_method?: string }>;
  quality: { errors: string[]; warnings: string[]; minimum_weight_coverage: number; news_missing_days: number;
    valuation_missing_values: number; constituent_coverage: Array<{date: string; ts_code: string; weight: number}> };
  files: Record<string, { sha256: string; bytes: number }>;
}
export interface MarketOverview {
  active_snapshot: MarketSnapshot | null; snapshots: MarketSnapshot[]; jobs: MarketSyncJob[]; source: DataSource;
  baseline_through: string | null; suggested_start_date: string | null; latest_closed_date: string;
  asset_definition_sha256: string;
  assets: { schema_version: number; effective_from: string; assets: Record<string, {
    name: string; base_currency: string; constituents: Array<{ts_code: string; name: string; weight: number; legacy_weight?: number}>;
  }> };
}
