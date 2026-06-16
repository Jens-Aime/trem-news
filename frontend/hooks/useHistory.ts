"use client";

import { useState, useEffect, useCallback } from "react";
import type { HistoryEntry, HistoryResponse } from "@/types/market";
import { resolveApiBase } from "@/lib/utils";

const REFRESH_INTERVAL_MS = 15_000;

export interface UseHistoryReturn {
  items: HistoryEntry[];
  total: number;
  page: number;
  pages: number;
  pageSize: number;
  isLoading: boolean;
  error: string | null;
  goToPage: (p: number) => void;
}

export function useHistory(pageSize: number = 20): UseHistoryReturn {
  const [items, setItems] = useState<HistoryEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPage = useCallback(
    async (p: number) => {
      setIsLoading(true);
      setError(null);
      try {
        const url = `${resolveApiBase()}/api/v1/history?page=${p}&page_size=${pageSize}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as HistoryResponse;
        setItems(data.items);
        setTotal(data.total);
        setPage(data.page);
        setPages(data.pages);
      } catch (e) {
        setError(String(e));
      } finally {
        setIsLoading(false);
      }
    },
    [pageSize]
  );

  useEffect(() => {
    fetchPage(page);
    const id = setInterval(() => fetchPage(page), REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchPage, page]);

  const goToPage = useCallback((p: number) => setPage(p), []);

  return { items, total, page, pages, pageSize, isLoading, error, goToPage };
}
