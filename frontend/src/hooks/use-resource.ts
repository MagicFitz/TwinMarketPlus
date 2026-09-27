import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";

export interface ResourceState<T> {
  data: T | null;
  loading: boolean;
  refreshing: boolean;
  error: ApiError | null;
  reload: () => void;
}

export function useResource<T>(loader: (signal: AbortSignal) => Promise<T>, dependencies: readonly unknown[] = [], interval = 0): ResourceState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [version, setVersion] = useState(0);
  const dataRef = useRef<T | null>(null);
  dataRef.current = data;
  const reload = useCallback(() => setVersion((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    let pending: AbortController | null = null;
    const load = async () => {
      pending?.abort();
      pending = new AbortController();
      dataRef.current ? setRefreshing(true) : setLoading(true);
      try {
        const value = await loader(pending.signal);
        if (active) { setData(value); setError(null); }
      } catch (reason) {
        if (active && !(reason instanceof DOMException && reason.name === "AbortError")) {
          setError(reason instanceof ApiError ? reason : new ApiError({ status: 0, code: "UNKNOWN", message: reason instanceof Error ? reason.message : "未知错误", retryable: false }));
        }
      } finally {
        if (active) { setLoading(false); setRefreshing(false); }
      }
    };
    void load();
    const timer = interval > 0 ? window.setInterval(load, interval) : undefined;
    return () => { active = false; pending?.abort(); if (timer) window.clearInterval(timer); };
    // The caller provides the intended dependency list, like React's built-in hooks.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...dependencies, version, interval]);

  return { data, loading, refreshing, error, reload };
}
