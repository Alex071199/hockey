"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { parseMatchDate } from "@/lib/parse-date";
import StreamPlayer from "@/components/StreamPlayer";
import MatchStats, { MatchStatsData } from "@/components/MatchStats";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface Stream { url: string; quality: string; source: string; }
interface Match {
  id: number; match_uid: string; league: string;
  team_home: string; team_away: string; datetime_utc: string;
  status: string; stream_urls: Stream[];
}

// Приоритет источников: сначала те, что обычно открываются без VPN из РФ
function sourcePriority(s: Stream) {
  const u = s.url;
  if (/vk\.com|vkvideo\.ru|vkvideo\.rs/.test(u)) return 0;
  if (/rutube\.ru/.test(u)) return 1;
  if (/ok\.ru/.test(u)) return 2;
  if (/embedded\.slevel\.ru/.test(u)) return 3;
  if (/\.m3u8/.test(u)) return 4;
  if (/youtube\.com|youtu\.be/.test(u)) return 5;
  if (/livetv/.test(u)) return 6;
  if (u.startsWith("acestream://")) return 7;
  return 8;
}

function sortStreams(list: Stream[]) {
  return [...list].sort((a, b) => sourcePriority(a) - sourcePriority(b));
}

export default function MatchPage() {
  const params = useParams();
  const [match, setMatch] = useState<Match | null>(null);
  const [selectedStream, setSelectedStream] = useState<Stream | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<MatchStatsData | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [statsError, setStatsError] = useState<string | null>(null);

  useEffect(() => {
    if (!params.id) return;
    fetch(`${API_URL}/api/schedule/${params.id}`)
      .then((r) => { if (!r.ok) throw new Error("Матч не найден"); return r.json(); })
      .then((data) => {
        setMatch(data);
        const ordered = sortStreams(data.stream_urls || []);
        if (ordered.length > 0) setSelectedStream(ordered[0]);
        if (data.status === "finished" && data.league === "KHL") {
          setStatsLoading(true);
          const date = (data.datetime_utc || "").slice(0, 10);
          fetch(
            `${API_URL}/api/match-stats?league=KHL&date=${date}&home=${encodeURIComponent(data.team_home)}&away=${encodeURIComponent(data.team_away)}`
          )
            .then((r) => { if (!r.ok) throw new Error(`Статистика недоступна (${r.status})`); return r.json(); })
            .then((s) => { setStats(s); setStatsError(null); })
            .catch((e) => setStatsError(e instanceof Error ? e.message : "Ошибка статистики"))
            .finally(() => setStatsLoading(false));
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [params.id]);

  if (loading) return (
    <div className="pt-24 pb-16 max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8">
      <div className="animate-pulse space-y-4">
        <div className="h-6 bg-hockey-card rounded w-32" />
        <div className="w-full h-[calc(100svh-100px)] min-h-[420px] bg-hockey-card rounded-xl" />
      </div>
    </div>
  );

  if (error || !match) return (
    <div className="pt-24 pb-16 max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 text-center">
      <p className="text-hockey-accent mb-4">{error || "Матч не найден"}</p>
      <Link href="/" className="text-hockey-text-secondary hover:text-white transition-colors">← Календарь</Link>
    </div>
  );

  const leagueLabel: Record<string, string> = { KHL: "КХЛ", VHL: "ВХЛ", MHL: "МХЛ" };

  const sortedStreams = sortStreams(match.stream_urls);

  return (
    <div className="pt-24 pb-16">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8">
        <Link href="/" className="inline-flex items-center gap-2 text-sm text-hockey-text-secondary hover:text-white transition-colors mb-6">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 19l-7-7 7-7"/></svg>
          Назад
        </Link>

        <div className="flex items-center gap-3 mb-2">
          <span className={`px-2.5 py-1 rounded text-[10px] font-bold tracking-wider uppercase ${
            match.league === "KHL" ? "bg-hockey-khl/20 text-hockey-khl" :
            match.league === "MHL" ? "bg-hockey-mhl/20 text-hockey-mhl" :
            "bg-hockey-vhl/20 text-hockey-vhl"
          }`}>
            {leagueLabel[match.league] || match.league}
          </span>
          {match.status === "live" && (
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-hockey-live animate-pulse-live" />
              <span className="text-[11px] font-bold text-hockey-live tracking-wider uppercase">Прямая трансляция</span>
            </div>
          )}
        </div>

        <h1 className="text-3xl font-black tracking-tight mb-1">
          {match.team_home} <span className="text-hockey-text-muted mx-2">vs</span> {match.team_away}
        </h1>
        <p className="text-sm text-hockey-text-secondary mb-6">
          {parseMatchDate(match.datetime_utc).toLocaleString("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}
        </p>

        {match.status === "finished" && match.league === "KHL" ? (
          <div className="mt-2">
            {statsLoading && (
              <div className="glass rounded-2xl p-6 space-y-3 animate-pulse" aria-hidden>
                {[90, 75, 85].map((w, i) => (
                  <div key={i} className="h-10 rounded-lg bg-hockey-card" style={{ width: `${w}%` }} />
                ))}
              </div>
            )}
            {statsError && !stats && (
              <div className="glass rounded-2xl p-6 text-center text-red-400 text-sm">
                Не удалось загрузить статистику: {statsError}
              </div>
            )}
            {stats && <MatchStats data={stats} />}
          </div>
        ) : (
          <>
            {sortedStreams.length > 0 && (
              <div className="flex gap-2 mb-4">
                {sortedStreams.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => setSelectedStream(s)}
                    className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all duration-200 ${
                      selectedStream?.url === s.url
                        ? "bg-hockey-accent text-white shadow-lg shadow-hockey-accent/20"
                        : "bg-hockey-card border border-hockey-border text-hockey-text-secondary hover:text-white hover:border-hockey-border-light"
                    }`}
                  >
                    {s.source === "livetv" ? "LiveTV" : s.source === "acestream" ? "AceStream" : s.source.startsWith("livetv_") ? `LiveTV • ${s.source.slice(7).toUpperCase()}` : s.source}
                  </button>
                ))}
              </div>
            )}

            {selectedStream && (
              <StreamPlayer url={selectedStream.url} title={`${match.team_home} vs ${match.team_away}`} />
            )}
          </>
        )}
      </div>
    </div>
  );
}
