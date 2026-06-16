"use client";

import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import type { HistoryEntry } from "@/types/market";
import {
  RISK_BADGE_CLASSES,
  SENTIMENT_BADGE_CLASSES,
  SENTIMENT_LABEL,
  formatConfidence,
  formatSurprisePct,
  formatEventDate,
} from "@/lib/utils";

interface HistoryTableProps {
  items: HistoryEntry[];
  total: number;
  page: number;
  pages: number;
  pageSize: number;
  isLoading: boolean;
  error: string | null;
  onPage: (p: number) => void;
}

export function HistoryTable({
  items,
  total,
  page,
  pages,
  isLoading,
  error,
  onPage,
}: HistoryTableProps) {
  if (error) {
    return (
      <div className="rounded border border-red-900/50 bg-red-950/30 px-4 py-3 text-sm text-red-400">
        Failed to load history: {error}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* ── Table ───────────────────────────────────────────────── */}
      <div className="relative overflow-x-auto rounded-lg border border-slate-800">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-950/60 z-10">
            <Loader2 className="h-5 w-5 animate-spin text-slate-500" />
          </div>
        )}
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-900/60">
              <th className="px-3 py-2.5 font-medium text-slate-400">Event</th>
              <th className="px-3 py-2.5 font-medium text-slate-400">Actual / Fcst</th>
              <th className="px-3 py-2.5 font-medium text-slate-400">Surprise</th>
              <th className="px-3 py-2.5 font-medium text-slate-400">Sentiment</th>
              <th className="px-3 py-2.5 font-medium text-slate-400">Risk</th>
              <th className="px-3 py-2.5 font-medium text-slate-400">Conf.</th>
              <th className="px-3 py-2.5 font-medium text-slate-400 whitespace-nowrap">Analyzed</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {items.length === 0 && !isLoading && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-slate-600">
                  No history yet
                </td>
              </tr>
            )}
            {items.map((item) => {
              const surprise = formatSurprisePct(item.surprise_pct);
              const beat = (item.surprise_pct ?? 0) >= 0;
              return (
                <tr key={`${item.event_id}-${item.analyzed_at}`} className="hover:bg-slate-900/40">
                  <td className="px-3 py-2 text-slate-200">
                    <div className="font-medium leading-tight">{item.event_name}</div>
                    <div className="text-slate-500">{item.country} · {item.currency}</div>
                  </td>
                  <td className="px-3 py-2 font-mono text-slate-300">
                    {item.actual != null ? item.actual : "—"}
                    {item.forecast != null && (
                      <span className="text-slate-600"> / {item.forecast}</span>
                    )}
                    {item.unit && (
                      <span className="ml-1 text-slate-600">{item.unit}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono">
                    {surprise ? (
                      <span className={beat ? "text-emerald-400" : "text-rose-400"}>
                        {surprise}
                      </span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${SENTIMENT_BADGE_CLASSES[item.sentiment]}`}>
                      {SENTIMENT_LABEL[item.sentiment]}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${RISK_BADGE_CLASSES[item.risk_level]}`}>
                      {item.risk_level}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-slate-300">
                    {formatConfidence(item.confidence_score)}
                  </td>
                  <td className="px-3 py-2 text-slate-500 whitespace-nowrap">
                    {formatEventDate(item.analyzed_at)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* ── Pagination ──────────────────────────────────────────── */}
      {pages > 1 && (
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>
            {total} event{total !== 1 ? "s" : ""} · page {page} of {pages}
          </span>
          <div className="flex gap-1">
            <button
              onClick={() => onPage(page - 1)}
              disabled={page <= 1}
              className="flex items-center gap-1 rounded border border-slate-700 bg-slate-800 px-2 py-1 hover:border-slate-600 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ChevronLeft className="h-3 w-3" /> Prev
            </button>
            <button
              onClick={() => onPage(page + 1)}
              disabled={page >= pages}
              className="flex items-center gap-1 rounded border border-slate-700 bg-slate-800 px-2 py-1 hover:border-slate-600 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next <ChevronRight className="h-3 w-3" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
