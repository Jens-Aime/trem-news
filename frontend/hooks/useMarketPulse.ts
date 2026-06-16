"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import type {
  AnalysisResult,
  ConnectionStatus,
  WSMessage,
} from "@/types/market";

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const WS_PATH = "/ws/market-pulse";
const MAX_EVENTS = 50;         // cap the in-memory feed length
const MAX_RECONNECT_ATTEMPTS = 10;

/**
 * Compute the WebSocket URL at runtime so it works both in local dev and in
 * proxied environments (e.g. GitHub Codespaces) where the port is embedded in
 * the hostname as "…-{port}.{domain}".
 *
 * Priority:
 *   1. localhost            → ws://localhost:8000/ws/market-pulse
 *   2. Proxy/tunnel host    → replace the embedded frontend port with 8000, use wss://
 *
 * Only called from inside connect(), which is triggered by useEffect — so
 * window is always defined at call-time.
 */
function resolveWsUrl(): string {
  if (typeof window === "undefined") {
    return `ws://localhost:8000${WS_PATH}`;
  }

  const { hostname, protocol } = window.location;

  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return `ws://localhost:8000${WS_PATH}`;
  }

  // Codespaces / any tunnel that embeds the port as "-PORT." in the hostname
  // e.g. "myapp-3000.app.github.dev" → "myapp-8000.app.github.dev"
  const wsScheme = protocol === "https:" ? "wss:" : "ws:";
  const backendHost = hostname.replace(/-\d+\./, "-8000.");
  return `${wsScheme}//${backendHost}${WS_PATH}`;
}

/** Exponential backoff capped at 30 s: 1 s, 2 s, 4 s, 8 s … 30 s */
function backoffDelay(attempt: number): number {
  return Math.min(1_000 * Math.pow(2, attempt), 30_000);
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook interface
// ─────────────────────────────────────────────────────────────────────────────

export interface UseMarketPulseOptions {
  url?: string;
  maxReconnectAttempts?: number;
}

export interface UseMarketPulseReturn {
  events: AnalysisResult[];
  status: ConnectionStatus;
  clientId: string | null;
  reconnectAttempt: number;
  clearEvents: () => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook implementation
// ─────────────────────────────────────────────────────────────────────────────

export function useMarketPulse({
  url,
  maxReconnectAttempts = MAX_RECONNECT_ATTEMPTS,
}: UseMarketPulseOptions = {}): UseMarketPulseReturn {
  const [events, setEvents] = useState<AnalysisResult[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [clientId, setClientId] = useState<string | null>(null);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptCountRef = useRef(0);
  const unmountedRef = useRef(false);

  const connect = useCallback(() => {
    if (unmountedRef.current) return;

    // Resolve URL here — runs only in the browser (inside useEffect), so
    // window is always defined. Prop > env override > runtime detection.
    const wsUrl = url ?? process.env.NEXT_PUBLIC_WS_URL ?? resolveWsUrl();

    // Clean up any existing socket before reconnecting
    if (wsRef.current) {
      wsRef.current.onclose = null; // prevent double reconnect
      wsRef.current.close();
      wsRef.current = null;
    }

    setStatus("connecting");

    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl);
    } catch {
      setStatus("error");
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      if (unmountedRef.current) return;
      attemptCountRef.current = 0;
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
        const result = msg.data;
        setEvents((prev) => [result, ...prev].slice(0, MAX_EVENTS));
      }
    };

    ws.onerror = () => {
      if (unmountedRef.current) return;
      setStatus("error");
    };

    ws.onclose = () => {
      if (unmountedRef.current) return;
      wsRef.current = null;
      setStatus("disconnected");
      setClientId(null);

      if (attemptCountRef.current < maxReconnectAttempts) {
        const delay = backoffDelay(attemptCountRef.current);
        attemptCountRef.current += 1;
        setReconnectAttempt(attemptCountRef.current);
        timerRef.current = setTimeout(connect, delay);
      }
    };
  }, [url, maxReconnectAttempts]);

  useEffect(() => {
    unmountedRef.current = false;
    connect();

    return () => {
      unmountedRef.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  const clearEvents = useCallback(() => setEvents([]), []);

  return { events, status, clientId, reconnectAttempt, clearEvents };
}
