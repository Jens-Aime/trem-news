"use client";

import { useState, useEffect, useRef } from "react";
import type { VolatilityAlert, VolatilityAlertsResponse } from "@/types/market";
import { resolveApiBase } from "@/lib/utils";

const POLL_INTERVAL_MS = 5_000;
const FRESHNESS_MS = 10 * 60 * 1000; // only surface alerts ≤ 10 min old

function isRecent(isoStr: string): boolean {
  return Date.now() - new Date(isoStr).getTime() < FRESHNESS_MS;
}

export interface UseVolatilityAlertsReturn {
  alerts: VolatilityAlert[];
  latestAlert: VolatilityAlert | null;
}

export function useVolatilityAlerts(
  pollInterval = POLL_INTERVAL_MS
): UseVolatilityAlertsReturn {
  const [alerts, setAlerts] = useState<VolatilityAlert[]>([]);
  const [latestAlert, setLatestAlert] = useState<VolatilityAlert | null>(null);
  const unmountedRef = useRef(false);

  useEffect(() => {
    unmountedRef.current = false;

    const poll = async () => {
      if (unmountedRef.current) return;
      try {
        const url = `${resolveApiBase()}/api/v1/volatility-alerts?limit=10`;
        const res = await fetch(url);
        if (!res.ok) return;
        const data = (await res.json()) as VolatilityAlertsResponse;
        if (unmountedRef.current) return;
        setAlerts(data.items);
        const fresh = data.items.find((a) => isRecent(a.detected_at)) ?? null;
        setLatestAlert(fresh);
      } catch {
        // Silently ignore — volatility alerts are best-effort
      }
    };

    poll();
    const id = setInterval(poll, pollInterval);
    return () => {
      unmountedRef.current = true;
      clearInterval(id);
    };
  }, [pollInterval]);

  return { alerts, latestAlert };
}
