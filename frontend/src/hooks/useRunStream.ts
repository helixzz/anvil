import { useEffect, useRef, useState } from "react";
import { wsUrl } from "@/api";

export interface LiveEvent {
  event: string;
  payload: Record<string, unknown>;
}

export function useRunStream(runId: string | null): {
  events: LiveEvent[];
  connected: boolean;
} {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!runId) return;
    setEvents([]);
    const ws = new WebSocket(wsUrl(`/ws/runs/${runId}`));
    wsRef.current = ws;
    ws.addEventListener("open", () => setConnected(true));
    ws.addEventListener("close", () => setConnected(false));
    ws.addEventListener("error", () => setConnected(false));
    ws.addEventListener("message", (ev) => {
      try {
        const msg = JSON.parse(ev.data as string) as LiveEvent;
        if (msg.event === "ping") return;
        setEvents((prev) => [...prev.slice(-500), msg]);
      } catch {
        void 0;
      }
    });
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [runId]);

  return { events, connected };
}
