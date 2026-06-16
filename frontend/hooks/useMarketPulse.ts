"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import type {
  AnalysisResult,
  ConnectionStatus,
  HistoryResponse,
  WSMessage,
} from "@/types/market";
import { resolveWsUrl, resolveApiBase } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const MAX_WS_FAILURES = 3;       // consecutive connect-failures before polling
const MAX_RECONNECT_ATTEMPTS = 10;
const BACKOFF_CAP_MS = 30_000;
const POLL_INTERVAL_MS = 3_000;
const MAX_EVENTS = 50;

function backoffMs(attempt: number): number {
  return Math.min(1_000 * Math.pow(2, attempt), BACKOFF_CAP_MS);
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook interface
// ─────────────────────────────────────────────────────────────────────────────

export interface UseMarketPulseOptions {
  wsUrl?: string;
  maxReconnectAttempts?: number;
}

export interface UseMarketPulseReturn {
  events: AnalysisResult[];
  status: ConnectionStatus;
  clientId: string | null;
  reconnectAttempt: number;
  clearEvents: () => void;
  /** Transport currently in use; "polling" activates after 3 WS failures. */
  mode: "ws" | "polling";
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook implementation
// ─────────────────────────────────────────────────────────────────────────────

export function useMarketPulse({
  wsUrl,
  maxReconnectAttempts = MAX_RECONNECT_ATTEMPTS,
}: UseMarketPulseOptions = {}): UseMarketPulseReturn {
  const [events, setEvents] = useState<AnalysisResult[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [clientId, setClientId] = useState<string | null>(null);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [mode, setMode] = useState<"ws" | "polling">("ws");

  // Refs — survive re-renders without triggering effects
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const wsFailuresRef = useRef(0);        // consecutive connection failures
  const wsAttemptCountRef = useRef(0);   // reconnect backoff counter
  const modeRef = useRef<"ws" | "polling">("ws");
  const unmountedRef = useRef(false);
  const seenIdsRef = useRef<Set<string>>(new Set());

  // ── Shared event ingestion ─────────────────────────────────────────────────

  const ingestEvents = useCallback((incoming: AnalysisResult[]) => {
    const unseen = incoming.filter(
      (e) => !seenIdsRef.current.has(e.event_id)
    );
    if (unseen.length === 0) return;
    unseen.forEach((e) => seenIdsRef.current.add(e.event_id));
    setEvents((prev) => [...unseen, ...prev].slice(0, MAX_EVENTS));
  }, []);

  // ── HTTP polling fallback ──────────────────────────────────────────────────

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    if (pollTimerRef.current || unmountedRef.current) return;
    modeRef.current = "polling";
    setMode("polling");

    const poll = async () => {
      if (unmountedRef.current) return;
      try {
        const url = `${resolveApiBase()}/api/v1/history?page=1&page_size=20`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as HistoryResponse;
        // HistoryEntry extends AnalysisResult — safe cast for the live feed
        ingestEvents(data.items as unknown as AnalysisResult[]);
        setStatus("connected");
      } catch {
        if (!unmountedRef.current) setStatus("error");
      }
    };

    poll(); // immediate
    pollTimerRef.current = setInterval(poll, POLL_INTERVAL_MS);
  }, [ingestEvents]);

  // ── WebSocket connection ───────────────────────────────────────────────────

  const connectWs = useCallback(() => {
    if (unmountedRef.current || modeRef.current === "polling") return;

    // Clean up any existing socket
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    setStatus("connecting");

    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl ?? resolveWsUrl());
    } catch {
      // new WebSocket() itself threw — treat as an immediate failure
      wsFailuresRef.current++;
      if (wsFailuresRef.current >= MAX_WS_FAILURES) startPolling();
      return;
    }
    wsRef.current = ws;

    let opened = false;

    ws.onopen = () => {
      if (unmountedRef.current) return;
      opened = true;
      wsFailuresRef.current = 0;
      wsAttemptCountRef.current = 0;
      setReconnectAttempt(0);
      setStatus("connected");
    };

    ws.onmessage = (ev: MessageEvent) => {
      if (unmountedRef.current) return;
      let msg: WSMessage;
      try {
        msg = JSON.parse(ev.data as string) as WSMessage;
      } catch {
        return;
      }
      if (msg.type === "connection_ack" && msg.client_id) {
        setClientId(msg.client_id);
      }
      if (msg.type === "analysis_result" && msg.data) {
        ingestEvents([msg.data as AnalysisResult]);
      }
    };

    ws.onerror = () => { /* onclose always fires after onerror */ };

    ws.onclose = () => {
      if (unmountedRef.current || modeRef.current === "polling") return;
      wsRef.current = null;
      setClientId(null);

      // Only count failures-to-connect, not drops of established sessions
      if (!opened) wsFailuresRef.current++;

      if (wsFailuresRef.current >= MAX_WS_FAILURES) {
        // Switch to polling — status stays "connected" once first poll succeeds
        startPolling();
        return;
      }

      setStatus("disconnected");
      if (wsAttemptCountRef.current < maxReconnectAttempts) {
        const delay = backoffMs(wsAttemptCountRef.current);
        wsAttemptCountRef.current++;
        setReconnectAttempt(wsAttemptCountRef.current);
        reconnectTimerRef.current = setTimeout(connectWs, delay);
      }
    };
  }, [wsUrl, maxReconnectAttempts, startPolling, ingestEvents]);

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  useEffect(() => {
    unmountedRef.current = false;
    // Reset failure tracking on fresh mount (handles React StrictMode double-invoke)
    wsFailuresRef.current = 0;
    wsAttemptCountRef.current = 0;
    modeRef.current = "ws";

    connectWs();

    return () => {
      unmountedRef.current = true;
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      stopPolling();
    };
  }, [connectWs, stopPolling]);

  const clearEvents = useCallback(() => {
    setEvents([]);
    seenIdsRef.current.clear();
  }, []);

  return { events, status, clientId, reconnectAttempt, clearEvents, mode };
}
