"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import MatchStats, { MatchStatsData } from "@/components/MatchStats";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

function StatsContent() {
  const searchParams = useSearchParams();
  const eventId = searchParams.get("event_id") || "";
  const date = searchParams.get("date") || "";
  const home = searchParams.get("home") || "";
  const away = searchParams.get("away") || "";

  const [data, setData] = useState<MatchStatsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!eventId && (!date || !home || !away)) {
      setError("Не указаны параметры матча");
      setLoading(false);
      return;
    }

    const url = eventId
      ? `${API_URL}/api/match-stats?event_id=${eventId}`
      : `${API_URL}/api/match-stats?league=KHL&date=${date}&home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}`;

    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`Статистика недоступна (${r.status})`);
        return r.json();
      })
      .then((s) => { setData(s); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : "Ошибка загрузки"))
      .finally(() => setLoading(false));
  }, [eventId, date, home, away]);

  return (
    <div className="pt-16 sm:pt-24 pb-4 sm:pb-16">
      <div className="max-w-[800px] mx-auto px-3 sm:px-6 lg:px-8">
        <Link
          href="/schedule"
          className="inline-flex items-center gap-2 text-sm text-hockey-text-secondary hover:text-white transition-colors mb-4 sm:mb-6"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M15 19l-7-7 7-7" />
          </svg>
          Календарь
        </Link>

        <h1 className="text-lg sm:text-2xl font-black tracking-tight mb-4 sm:mb-6">
          {data ? `${data.match.home} — ${data.match.away}` : `${home || "..."} — ${away || "..."}`}
        </h1>

        {loading && (
          <div className="glass rounded-2xl p-6 space-y-3 animate-pulse" aria-hidden>
            {[90, 75, 85].map((w, i) => (
              <div key={i} className="h-10 rounded-lg bg-hockey-card" style={{ width: `${w}%` }} />
            ))}
          </div>
        )}

        {error && (
          <div className="glass rounded-2xl p-6 text-center text-red-400 text-sm">
            {error}
          </div>
        )}

        {data && <MatchStats data={data} tabs />}
      </div>
    </div>
  );
}

export default function StatsPage() {
  return (
    <Suspense fallback={
      <div className="pt-16 sm:pt-24 pb-4 sm:pb-16 max-w-[800px] mx-auto px-3 sm:px-6 lg:px-8">
        <div className="glass rounded-2xl p-6 space-y-3 animate-pulse" aria-hidden>
          {[90, 75, 85].map((w, i) => (
            <div key={i} className="h-10 rounded-lg bg-hockey-card" style={{ width: `${w}%` }} />
          ))}
        </div>
      </div>
    }>
      <StatsContent />
    </Suspense>
  );
}
