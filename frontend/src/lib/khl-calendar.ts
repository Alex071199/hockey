"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
const STORAGE_KEY = "khl_calendar_v1";
const STORAGE_TTL_MS = 60 * 60 * 1000;
/** Первичная сборка календаря на бэкенде занимает ~3 минуты. */
const MAX_READY_RETRIES = 45;
const RETRY_DELAY_MS = 5000;

export interface KhlCalendarMatch {
  id?: number | null;
  date: string;
  time: string;
  home: string;
  away: string;
  status?: string;
  score_home?: number | null;
  score_away?: number | null;
}

interface LoadResult {
  matches: KhlCalendarMatch[];
  ready: boolean;
}

let memoryCache: KhlCalendarMatch[] | null = null;
let inflight: Promise<LoadResult> | null = null;

function readStored(): KhlCalendarMatch[] | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (
      parsed &&
      Array.isArray(parsed.matches) &&
      parsed.matches.length > 0 &&
      Date.now() - (parsed.at || 0) < STORAGE_TTL_MS
    ) {
      return parsed.matches as KhlCalendarMatch[];
    }
  } catch {}
  return null;
}

function store(matches: KhlCalendarMatch[]) {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ at: Date.now(), matches })
    );
  } catch {}
}

function load(): Promise<LoadResult> {
  if (memoryCache) return Promise.resolve({ matches: memoryCache, ready: true });
  if (inflight) return inflight;
  const stored = readStored();
  if (stored) {
    memoryCache = stored;
    return Promise.resolve({ matches: stored, ready: true });
  }
  const p: Promise<LoadResult> = fetch(`${API_URL}/api/khl/calendar`, {
    cache: "no-store",
  })
    .then((r) => (r.ok ? r.json() : null))
    .then((d): LoadResult => {
      const matches: KhlCalendarMatch[] = Array.isArray(d?.matches)
        ? d.matches
        : [];
      const ready = Boolean(d?.ready) || matches.length > 0;
      if (matches.length > 0) {
        memoryCache = matches;
        store(matches);
      }
      return { matches, ready };
    })
    .catch((): LoadResult => ({ matches: [], ready: false }));
  inflight = p;
  p.then(() => {
    if (inflight === p) inflight = null;
  });
  return p;
}

/**
 * KHL-календарь всего сезона с официального API. Загружается один раз
 * (память + sessionStorage) и потом только показывается.
 */
export function useKhlCalendar(): {
  matches: KhlCalendarMatch[];
  loading: boolean;
} {
  const [matches, setMatches] = useState<KhlCalendarMatch[]>(
    memoryCache ?? []
  );
  const [loading, setLoading] = useState(!memoryCache);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const attempt = (n: number) => {
      load().then(({ matches: m, ready }) => {
        if (!alive) return;
        if (m.length > 0) {
          setMatches(m);
          setLoading(false);
          return;
        }
        if (ready || n >= MAX_READY_RETRIES) {
          setLoading(false);
          return;
        }
        timer = setTimeout(() => attempt(n + 1), RETRY_DELAY_MS);
      });
    };
    attempt(0);

    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, []);

  return { matches, loading };
}
