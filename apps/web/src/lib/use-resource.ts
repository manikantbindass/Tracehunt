"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "./api";

/** Keep the last successful snapshot visible while refreshing; discard stale requests. */
export function useResource<T>(path: string, refreshKey = 0, interval = 30000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const generation = useRef(0);
  const reload = useCallback(async () => {
    const current = ++generation.current;
    setRefreshing(true);
    try {
      const result = await api<T>(path);
      if (generation.current === current) { setData(result); setError(""); }
    } catch (err) {
      if (generation.current === current) setError(errorMessage(err));
    } finally {
      if (generation.current === current) { setLoading(false); setRefreshing(false); }
    }
  }, [path]);
  useEffect(() => {
    setData(null); setLoading(true); setError("");
    void reload();
    const timer = interval ? setInterval(() => { if (!document.hidden) void reload(); }, interval) : null;
    return () => { generation.current++; if (timer) clearInterval(timer); };
  }, [reload, refreshKey, interval]);
  return { data, error, loading, refreshing, reload };
}

export function useDebounced(value: string, delay = 300) {
  const [settled, setSettled] = useState(value);
  useEffect(() => { const timer = setTimeout(() => setSettled(value), delay); return () => clearTimeout(timer); }, [value, delay]);
  return settled;
}
