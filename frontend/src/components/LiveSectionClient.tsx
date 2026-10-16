"use client";

import { useState, useCallback, useEffect } from "react";
import Link from "next/link";
import MatchCard from "@/components/MatchCard";
import { useWebSocket, WsMatch } from "@/lib/useWebSocket";
import { useFavorites } from "@/lib/FavoritesContext";
import { parseMatchDate } from "@/lib/parse-date";
import { useScoreToggle } from "@/context/ScoreToggleContext";
import { fetchKhlUpcoming } from "@/lib/khl-api-times";

interface Match {
  id: number;
  match_uid: string;
  league: string;
  team_home: string;
  team_away: string;
  datetime_utc: string;
  status: string;
  added_live?: boolean;
  stream_urls: { url: string; quality: string; source: string }[];
  home_score?: number | null;
  away_score?: number | null;
}

function mergeUpdated(prev: Match[], updated: WsMatch[]): Match[] {
  const map = new Map(prev.map((m) => [m.id, m]));
  for (const m of updated) {
    const existing = map.get(m.id);
    map.set(
      m.id,
      existing
        ? { ...existing, ...m }
        : ({ ...m, match_uid: m.match_uid ?? `ws_${m.id}` } as Match)
    );
  }
  return Array.from(map.values());
}

export default function LiveSectionClient({ initialMatches }: { initialMatches: Match[] }) {
  const [matches, setMatches] = useState<Match[]>(initialMatches);
  const { favorites } = useFavorites();
  const { showScores, toggleScores } = useScoreToggle();

  const isFavMatch = useCallback(
    (m: Match) => favorites.includes(m.team_home) || favorites.includes(m.team_away),
    [favorites]
  );

  const handleMatchesUpdate = useCallback((updated: WsMatch[]) => {
    setMatches((prev) => mergeUpdated(prev, updated));
  }, []);

  const handleScoresUpdate = useCallback((updated: WsMatch[]) => {
    setMatches((prev) => mergeUpdated(prev, updated));
  }, []);

  const { connected } = useWebSocket(handleMatchesUpdate, handleScoresUpdate);

  // Polling fallback: обновляем счета с сервера, если WebSocket недоступен.
  // /api/schedule отдаёт массив матчей (не { results: [...] }).
  useEffect(() => {
    const fetchScores = async () => {
      try {
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"}/api/schedule`);
        if (!res.ok) return;
        const data = await res.json();
        const list: Match[] = Array.isArray(data) ? data : [];
        const byId = new Map(list.map((m) => [m.id, m]));
        setMatches((prev) =>
          prev.map((m) => {
            const upd = byId.get(m.id);
            return upd
              ? { ...m, home_score: upd.home_score, away_score: upd.away_score, status: upd.status }
              : m;
          })
        );
      } catch (e) {
        console.error("Ошибка при обновлении счетов:", e);
      }
    };

    fetchScores();
    const interval = setInterval(fetchScores, 15_000);
    return () => clearInterval(interval);
  }, []);

  // Позже начавшиеся — вверху, давно идущие опускаются вниз;

  // Позже начавшиеся — вверху, давно идущие опускаются вниз;
  // матчи команд из избранного всегда в начале списка
  const liveMatches = matches
    .filter((m) => m.status === "live" && m.stream_urls.length > 0)
    .sort((a, b) => {
      const favDiff = Number(isFavMatch(b)) - Number(isFavMatch(a));
      if (favDiff !== 0) return favDiff;
      return parseMatchDate(b.datetime_utc).getTime() - parseMatchDate(a.datetime_utc).getTime();
    });
  const favoriteLive = liveMatches.filter(isFavMatch);
  const otherLive = liveMatches.filter((m) => !isFavMatch(m));
  const upcomingMatches = matches.filter((m) => m.status === "pre_game" && m.stream_urls.length > 0);

  return (
    <section id="live" className="py-16">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between gap-2 mb-8">
          <div className="flex items-center gap-2 sm:gap-3 min-w-0">
            {liveMatches.length > 0 && <span className="w-2 h-2 sm:w-2.5 sm:h-2.5 rounded-full bg-hockey-live animate-pulse-live shrink-0" />}
            <h2 className="text-sm sm:text-2xl font-black tracking-tight uppercase whitespace-nowrap min-w-0 truncate">
              {liveMatches.length > 0 ? "Сейчас в эфире" : "Матчи"}
            </h2>
            {connected && liveMatches.length > 0 && (
              <span className="hidden sm:inline ml-2 text-[9px] font-bold text-hockey-live/60 tracking-wider uppercase">LIVE</span>
            )}
          </div>
          <div className="flex items-center gap-2 sm:gap-3 shrink-0 whitespace-nowrap">
            <button
              onClick={toggleScores}
              className="text-xs sm:text-sm px-2 sm:px-3 py-1 rounded-lg bg-hockey-accent text-white font-bold hover:bg-hockey-accent/90 transition-colors"
              title="Показать/скрыть счёт"
            >
              {showScores ? "Скрыть счёт" : "Показать счёт"}
            </button>
            <Link href="/schedule" className="text-xs sm:text-sm text-hockey-text-secondary hover:text-white transition-colors">
              Все матчи →
            </Link>
          </div>
        </div>

        {liveMatches.length > 0 && (
          <div className="mb-16">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {favoriteLive.length > 0 && (
                <div className="col-span-full flex items-center gap-3">
                  <span className="flex items-center gap-1.5 text-[10px] sm:text-[11px] font-bold uppercase tracking-widest text-hockey-accent">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                    </svg>
                    Ваши матчи
                  </span>
                  <div className="flex-1 h-px bg-hockey-accent/25" />
                  <span className="text-[10px] font-bold tabular-nums text-hockey-accent/70">{favoriteLive.length}</span>
                </div>
              )}
              {favoriteLive.map((match) => (
                <MatchCard key={match.id} match={match} featured />
              ))}
              {otherLive.length > 0 && favoriteLive.length > 0 && (
                <div className="col-span-full flex items-center gap-3">
                  <div className="flex-1 h-px bg-hockey-border" />
                  <span className="text-[10px] uppercase tracking-widest text-hockey-text-muted">Остальные матчи</span>
                  <div className="flex-1 h-px bg-hockey-border" />
                </div>
              )}
              {otherLive.map((match) => (
                <MatchCard key={match.id} match={match} featured />
              ))}
            </div>
          </div>
        )}

        {liveMatches.length === 0 && upcomingMatches.length === 0 && (
          <div className="mb-16 text-center">
            <div className="glass rounded-2xl p-12">
              <p className="text-hockey-text-secondary text-lg">Игры скоро появятся</p>
            </div>
          </div>
        )}

        {upcomingMatches.length > 0 && (
          <div>
            {liveMatches.length === 0 && (
              <h3 className="text-lg font-bold text-hockey-text-muted mb-6 uppercase tracking-tight">Ближайшие матчи</h3>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {upcomingMatches.map((match) => (
                <MatchCard key={match.id} match={match} />
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
