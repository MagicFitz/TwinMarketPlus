import { useEffect, useRef, useState } from "react";
import type { RuntimeEvent } from "@/lib/api-types";
import { apiUrl } from "@/lib/runtime-config";

export type ConnectionState = "connecting" | "open" | "retrying" | "closed";

export function acceptEventId(eventId: number, cursor: number, seen: Set<number>) {
  return Number.isInteger(eventId) && eventId > cursor && !seen.has(eventId);
}

export function useRunEvents(runId: string, snapshotCursor = 0) {
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const cursorRef = useRef(snapshotCursor);

  useEffect(() => {
    const storageKey = `twinmarket:event-cursor:${runId}`;
    const saved = Number(sessionStorage.getItem(storageKey) || 0);
    cursorRef.current = Math.max(snapshotCursor, Number.isFinite(saved) ? saved : 0);
    let source: EventSource | null = null;
    let timer: number | undefined;
    let closed = false;
    let retry = 0;
    const seen = new Set<number>();

    const connect = () => {
      if (closed) return;
      setConnection(retry ? "retrying" : "connecting");
      source = new EventSource(`${apiUrl(`/runs/${encodeURIComponent(runId)}/events`)}?last_event_id=${cursorRef.current}`);
      source.onopen = () => { retry = 0; setConnection("open"); };
      source.addEventListener("runtime", (message) => {
        try {
          const event = JSON.parse((message as MessageEvent<string>).data) as RuntimeEvent;
          if (!acceptEventId(event.event_id, cursorRef.current, seen)) return;
          seen.add(event.event_id);
          if (seen.size > 500) seen.delete(seen.values().next().value as number);
          cursorRef.current = event.event_id;
          sessionStorage.setItem(storageKey, String(event.event_id));
          setEvents((current) => [event, ...current].slice(0, 100));
        } catch { /* malformed events are ignored without poisoning the stream */ }
      });
      source.onerror = () => {
        source?.close();
        if (closed) return;
        setConnection("retrying");
        const delay = Math.min(15_000, 1_000 * 2 ** Math.min(retry++, 4));
        timer = window.setTimeout(connect, delay);
      };
    };

    connect();
    return () => { closed = true; if (timer) window.clearTimeout(timer); source?.close(); setConnection("closed"); };
  }, [runId]);

  return { events, connection, cursor: cursorRef.current };
}
