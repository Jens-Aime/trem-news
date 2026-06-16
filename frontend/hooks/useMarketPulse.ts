"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { AnalysisResult, ConnectionStatus } from "@/types/market";

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const API_PATH = "/api/v1/latest-events";
const POLL_INTERVAL_MS = 2_000;
const MAX_EVENTS = 50;

/**
 * Resolve the backend base URL at runtime.
 *
 * Priority:
 *   1. NEXT_PUBLIC_API_URL env override (set in .env.local for explicit control)
 *   2. localhost / 127.0.0.1  → http://localhost:8000
 *   3. Codespaces / proxy tunnel → replace the embedded frontend port with 8000,
 *      e.g. "myapp-3000.app.github.dev" → "https://myapp-8000.app.github.dev"
 */
function resolveApiUrl(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return `${process.env.NEXT_PUBLIC_API_URL}${API_PATH}`;
  }
  if (typeof window === "undefined") {
    return `http://localhost:8000${API_PATH}`;
  }
  const { hostname, protocol } = window.location;
  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return `http://localhost:8000${API_PATH}`;
  }
  // Codespaces embeds the port as "-PORT." in the hostname
  const httpScheme = protocol === "https:" ? "https:" : "http:";
  const backendHost = hostname.replace(/-\d+\./, "-8000.");
  return `${httpScheme}//${backendHost}${API_PATH}`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook interface
// ─────────────────────────────────────────────────────────────────────────────

export interface UseMarketPulseOptions {
  url?: string;               // explicit API URL override
  maxReconnectAttempts?: number; // unused; kept for API compatibility
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
}: UseMarketPulseOptions = {}): UseMarketPulseReturn {
  const [events, setEvents] = useState<AnalysisResult[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const seenIdsRef = useRef<Set<string>>(new Set());

  const poll = useCallback(async () => {
    const apiUrl = url ?? resolveApiUrl();
    try {
      const res = await fetch(apiUrl);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const fresh = (await res.json()) as AnalysisResult[];

      // Only add events not already in the list
      const unseen = fresh.filter((e) => !seenIdsRef.current.has(e.event_id));
      if (unseen.length > 0) {
        unseen.forEach((e) => seenIdsRef.current.add(e.event_id));
        setEvents((prev) => [...unseen, ...prev].slice(0, MAX_EVENTS));
      }
      setStatus("connected");
    } catch {
      setStatus("error");
    }
  }, [url]);

  useEffect(() => {
    poll(); // immediate first fetch
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [poll]);

  const clearEvents = useCallback(() => {
    setEvents([]);
    seenIdsRef.current.clear();
  }, []);

  return { events, status, clientId: null, reconnectAttempt: 0, clearEvents };
}
