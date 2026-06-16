"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import type {
  AnalysisResult,
  ConnectionStatus,
  HistoryResponse,
} from "@/types/market";
import { resolveApiBase } from "@/lib/utils";

const POLL_INTERVAL_MS = 3_000;
const MAX_EVENTS = 50;

export interface UseMarketPulseOptions {
  pollInterval?: number;
}

export interface UseMarketPulseReturn {
  events: AnalysisResult[];
  status: ConnectionStatus;
  clearEvents: () => void;
}

export function useMarketPulse({
  pollInterval = POLL_INTERVAL_MS,
}: UseMarketPulseOptions = {}): UseMarketPulseReturn {
  const [events, setEvents] = useState<AnalysisResult[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");

  const seenIdsRef = useRef<Set<string>>(new Set());
  const unmountedRef = useRef(false);

  const ingestEvents = useCallback((incoming: AnalysisResult[]) => {
    const unseen = incoming.filter(
      (e) => !seenIdsRef.current.has(e.event_id)
    );
    if (unseen.length === 0) return;
    unseen.forEach((e) => seenIdsRef.current.add(e.event_id));
    setEvents((prev) => [...unseen, ...prev].slice(0, MAX_EVENTS));
  }, []);

  useEffect(() => {
    unmountedRef.current = false;

    const poll = async () => {
      if (unmountedRef.current) return;
      try {
        const url = `${resolveApiBase()}/api/v1/history?page=1&page_size=20`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as HistoryResponse;
        if (unmountedRef.current) return;
        // HistoryEntry extends AnalysisResult — safe cast for live feed display
        ingestEvents(data.items as unknown as AnalysisResult[]);
        setStatus("connected");
      } catch {
        if (!unmountedRef.current) setStatus("error");
      }
    };

    poll();
    const id = setInterval(poll, pollInterval);

    return () => {
      unmountedRef.current = true;
      clearInterval(id);
    };
  }, [ingestEvents, pollInterval]);

  const clearEvents = useCallback(() => {
    setEvents([]);
    seenIdsRef.current.clear();
  }, []);

  return { events, status, clearEvents };
}
