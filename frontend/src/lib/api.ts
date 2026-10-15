import type { DataSource, DataSourceUpdate, MarketOverview, MarketSnapshot, MarketSyncCreate, MarketSyncJob } from "./market-types";
import type { AgentMember, DocumentItem, DocumentList, EmbeddingModelSettings, EmbeddingModelUpdate, LanguageModelSettings, LanguageModelUpdate, MarketData, ModelSettings, PagedResult, Run, RunCreate, RunList, RunStatus, RuntimeSnapshot } from "./api-types";
import { apiUrl } from "./runtime-config";

export interface ApiErrorShape {
  status: number;
  code: string;
  message: string;
  details?: unknown;
  retryable: boolean;
}

export class ApiError extends Error implements ApiErrorShape {
  status: number;
  code: string;
  details?: unknown;
  retryable: boolean;

  constructor(error: ApiErrorShape) {
    super(error.message);
    this.name = "ApiError";
    this.status = error.status;
    this.code = error.code;
    this.details = error.details;
    this.retryable = error.retryable;
  }
}

function query(values: Record<string, string | number | boolean | undefined>) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => value !== undefined && params.set(key, String(value)));
  const output = params.toString();
  return output ? `?${output}` : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...init,
      headers: { Accept: "application/json", ...(init.body ? { "Content-Type": "application/json" } : {}), ...init.headers },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError({ status: 0, code: "NETWORK_ERROR", message: "无法连接 TwinMarket API，请检查本地服务。", details: error, retryable: true });
  }
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => ({})) as { error?: string; detail?: string; code?: string };
  if (!response.ok) {
    throw new ApiError({
      status: response.status,
      code: payload.code || `HTTP_${response.status}`,
      message: payload.error || payload.detail || "请求失败",
      details: payload,
      retryable: response.status === 0 || response.status === 408 || response.status === 429 || response.status >= 500,
    });
  }
  return payload as T;
}

export const api = {
  runs: {
    list: (options: { status?: RunStatus; archived?: boolean; signal?: AbortSignal } = {}) => request<RunList>(`/runs${query({ status: options.status, archived: options.archived })}`, { signal: options.signal }),
    get: (runId: string, signal?: AbortSignal) => request<Run>(`/runs/${encodeURIComponent(runId)}`, { signal }),
    create: (body: RunCreate, signal?: AbortSignal) => request<Run>("/runs", { method: "POST", body: JSON.stringify(body), signal }),
    action: (runId: string, action: "start" | "stop" | "resume" | "copy" | "archive", signal?: AbortSignal) => request<Run>(`/runs/${encodeURIComponent(runId)}/${action}`, { method: "POST", signal }),
    runtime: (runId: string, signal?: AbortSignal) => request<RuntimeSnapshot>(`/runs/${encodeURIComponent(runId)}/runtime`, { signal }),
    results: (runId: string, kind: "summary" | "trades" | "agents", page = 1, signal?: AbortSignal) => request<PagedResult>(`/runs/${encodeURIComponent(runId)}/results/${kind}${query({ page })}`, { signal }),
    agents: (runId: string, search = "", page = 1, signal?: AbortSignal) => request<PagedResult<AgentMember>>(`/runs/${encodeURIComponent(runId)}/agents${query({ q: search, page })}`, { signal }),
    agent: (runId: string, agentId: string, signal?: AbortSignal) => request<AgentMember>(`/runs/${encodeURIComponent(runId)}/agents/${encodeURIComponent(agentId)}`, { signal }),
    market: (runId: string, asset?: string, signal?: AbortSignal) => request<MarketData>(`/runs/${encodeURIComponent(runId)}/market${query({ asset })}`, { signal }),
  },
  market: {
    overview: (signal?: AbortSignal) => request<MarketOverview>("/market/overview", { signal }),
    snapshots: (signal?: AbortSignal) => request<{items: MarketSnapshot[]}>("/market/snapshots", { signal }),
    snapshot: (id: string, signal?: AbortSignal) => request<MarketSnapshot>(`/market/snapshots/${encodeURIComponent(id)}`, { signal }),
    activate: (id: string) => request<MarketSnapshot>(`/market/snapshots/${encodeURIComponent(id)}/activate`, { method: "POST" }),
    sync: (body: MarketSyncCreate) => request<MarketSyncJob>("/market/sync-jobs", { method: "POST", body: JSON.stringify(body) }),
    job: (id: string, signal?: AbortSignal) => request<MarketSyncJob>(`/market/sync-jobs/${encodeURIComponent(id)}`, { signal }),
    cancel: (id: string) => request<MarketSyncJob>(`/market/sync-jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  },
  documentation: {
    list: (signal?: AbortSignal) => request<DocumentList>("/documentation", { signal }),
    get: (path: string, signal?: AbortSignal) => request<DocumentItem>(`/documentation${query({ path })}`, { signal }),
  },
  settings: {
    dataSources: (signal?: AbortSignal) => request<{items: DataSource[]}>("/settings/data-sources", { signal }),
    updateTushare: (body: DataSourceUpdate) => request<DataSource>("/settings/data-sources/tushare", { method: "PUT", body: JSON.stringify(body) }),
    testTushare: () => request<DataSource>("/settings/data-sources/tushare/test", { method: "POST" }),
    models: (signal?: AbortSignal) => request<ModelSettings>("/settings/models", { signal }),
    updateLanguage: (body: LanguageModelUpdate, signal?: AbortSignal) => request<LanguageModelSettings>("/settings/models/language", { method: "PUT", body: JSON.stringify(body), signal }),
    updateEmbedding: (body: EmbeddingModelUpdate, signal?: AbortSignal) => request<EmbeddingModelSettings>("/settings/models/embedding", { method: "PUT", body: JSON.stringify(body), signal }),
  },
};
