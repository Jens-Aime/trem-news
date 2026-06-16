"use client";

import { History } from "lucide-react";
import { SurpriseChart } from "@/components/SurpriseChart";
import { HistoryTable } from "@/components/HistoryTable";
import { useHistory } from "@/hooks/useHistory";

export function HistoricalView() {
  const { items, total, page, pages, pageSize, isLoading, error, goToPage } =
    useHistory(20);

  return (
    <section className="space-y-4">
      {/* ── Section header ────────────────────────────────────── */}
      <div className="flex items-center gap-2">
        <History className="h-4 w-4 text-slate-500" />
        <h2 className="text-sm font-semibold text-slate-300">
          Historical Analysis
        </h2>
        {total > 0 && (
          <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
            {total}
          </span>
        )}
      </div>

      {/* ── Surprise chart ────────────────────────────────────── */}
      {items.length > 0 && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/30 px-4 py-3">
          <p className="mb-2 text-xs font-medium text-slate-500 uppercase tracking-wider">
            Surprise % — last {Math.min(items.length, 20)} events
          </p>
          <SurpriseChart items={items} />
        </div>
      )}

      {/* ── Data table ────────────────────────────────────────── */}
      <HistoryTable
        items={items}
        total={total}
        page={page}
        pages={pages}
        pageSize={pageSize}
        isLoading={isLoading}
        error={error}
        onPage={goToPage}
      />
    </section>
  );
}
