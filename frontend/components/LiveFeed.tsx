"use client";

import { useRef, useEffect } from "react";
import { Rss } from "lucide-react";
import { EventCard } from "@/components/EventCard";
import type { AnalysisResult } from "@/types/market";

interface LiveFeedProps {
  events: AnalysisResult[];
  onClear: () => void;
}

export function LiveFeed({ events, onClear }: LiveFeedProps) {
  const topRef = useRef<HTMLDivElement>(null);
  const prevLengthRef = useRef(0);

  // Scroll to top when a new event arrives
  useEffect(() => {
    if (events.length > prevLengthRef.current && topRef.current) {
      topRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    prevLengthRef.current = events.length;
  }, [events.length]);

  return (
    <section className="space-y-3">
      {/* ── Feed header ─────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-300">
          <Rss className="h-4 w-4 text-slate-500" />
          Live Event Feed
          {events.length > 0 && (
            <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
              {events.length}
            </span>
          )}
        </h2>
        {events.length > 0 && (
          <button
            onClick={onClear}
            className="rounded border border-slate-700 bg-slate-800 px-3 py-1 text-xs text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-300"
          >
            Clear
          </button>
        )}
      </div>

      {/* ── Scroll anchor ───────────────────────────────────── */}
      <div ref={topRef} />

      {/* ── Empty state ─────────────────────────────────────── */}
      {events.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-800 py-16 text-center">
          <Rss className="mb-3 h-8 w-8 text-slate-700" />
          <p className="text-sm text-slate-500">
            Waiting for market events…
          </p>
          <p className="mt-1 text-xs text-slate-700">
            Events will appear here when the AI analyses an economic release.
          </p>
        </div>
      )}

      {/* ── Event cards ─────────────────────────────────────── */}
      <div className="space-y-3">
        {events.map((event, idx) => (
          <EventCard
            key={`${event.event_id}-${event.analyzed_at}`}
            event={event}
            isNew={idx === 0}
          />
        ))}
      </div>
    </section>
  );
}
