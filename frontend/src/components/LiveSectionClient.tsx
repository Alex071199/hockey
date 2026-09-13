"use client";

import { useState, useCallback, useEffect } from "react";
import Link from "next/link";
import MatchCard from "@/components/MatchCard";
import { useWebSocket, WsMatch } from "@/lib/useWebSocket";
import { useFavorites } from "@/lib/FavoritesContext";
import { parseMatchDate } from "@/lib/parse-date";

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
}

function mergeUpdated(prev: Match[], updated: WsMatch[]): Match[] {
  const map = new Map(prev.map((m) => [m.id, m]));
  for (const m of updated) {
    const existing = map.get(m.id);
    map.set(
      m.id,
      existing
        ? { ...existing, ...m }
        : ({ ...m, match_uid: m.onhockey_id ?? `ws_${m.id}` } as Match)
    );
  }
  return Array.from(map.values());
}

export default function LiveSectionClient({ initialMatches }: { initialMatches: Match[] }) {  const [matches, setMatches] = useState<Match[]>(initialMatches);
  const { isFavorite } = useFavorites();

  const handleMatchesUpdate = useCallback((updated: WsMatch[]) => {
    setMatches((prev) => mergeUpdated(prev, updated));
  }, []);

  const handleScoresUpdate = useCallback((updated: WsMatch[]) => {
    setMatches((prev) => mergeUpdated(prev, updated));
  }, []);

  const { connected } = useWebSocket(handleMatchesUpdate, handleScoresUpdate);

  // Позже начавшиеся — вверху, давно идущие опускаются вниз
  const liveMatches = matches
    .filter((m) => m.status === "live" && m.stream_urls.length > 0)
    .sort((a, b) => parseMatchDate(b.datetime_utc).getTime() - parseMatchDate(a.datetime_utc).getTime());
  const upcomingMatches = matches.filter((m) => m.status === "pre_game" && m.stream_urls.length > 0);

  return (
    <section id="live" className="py-16">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            {liveMatches.length > 0 && <span className="w-2.5 h-2.5 rounded-full bg-hockey-live animate-pulse-live" />}
            <h2 className="text-2xl font-black tracking-tight uppercase">
              {liveMatches.length > 0 ? "Сейчас в эфире" : "Матчи"}
            </h2>
            {connected && liveMatches.length > 0 && (
              <span className="ml-2 text-[9px] font-bold text-hockey-live/60 tracking-wider uppercase">LIVE</span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <Link href="/schedule" className="text-sm text-hockey-text-secondary hover:text-white transition-colors">
              Все матчи →
            </Link>
          </div>
        </div>

        {liveMatches.length > 0 && (
          <div className="mb-16">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {liveMatches.map((match) => {
                const fav = isFavorite(match.team_home) || isFavorite(match.team_away);
                return (
                  <MatchCard key={match.id} match={match} featured isFavorite={fav} />
                );
              })}
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
