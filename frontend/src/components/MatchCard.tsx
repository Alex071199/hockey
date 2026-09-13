"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getTeamLogo } from "@/lib/team-logos";
import { parseMatchDate } from "@/lib/parse-date";
import RemindButton from "@/components/RemindButton";

interface Match {
  id: number;
  match_uid: string;
  league: string;
  team_home: string;
  team_away: string;
  datetime_utc: string;
  status: string;
  stream_urls: { url: string; quality: string; source: string }[];
}

export default function MatchCard({ match, featured = false, isFavorite = false, score = null, finish = null }: { match: Match; featured?: boolean; isFavorite?: boolean; score?: string | null; finish?: string | null }) {
  const [countdown, setCountdown] = useState("");

  // Логотипы показываем только для матчей КХЛ
  const showLogos = match.league === "KHL";

  useEffect(() => {
    if (match.status !== "pre_game") return;
    const update = () => {
      const diff = parseMatchDate(match.datetime_utc).getTime() - Date.now();
      if (diff <= 0) { setCountdown(""); return; }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setCountdown(`${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`);
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [match.status, match.datetime_utc]);

  return (
    <Link href={`/match/${match.id}`}>
      <div
        className={`group relative rounded-xl overflow-hidden transition-all duration-300 card-hover ${
          isFavorite && match.status === "live"
            ? "bg-hockey-accent/10 border border-hockey-accent/30 animate-glow-red"
            : featured
              ? "bg-hockey-accent/10 border border-hockey-accent/30 animate-glow-red"
              : "bg-hockey-card border border-hockey-border hover:border-hockey-border-light"
        }`}
      >
        <div className="absolute inset-0 bg-gradient-to-r from-hockey-accent/0 via-hockey-accent/[0.02] to-hockey-accent/0 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />

        <div className="relative p-3 sm:p-5">
          <div className="flex items-center justify-between mb-3 sm:mb-4">
            <img
              src={`/${match.league}.svg`}
              alt={match.league}
              className="h-4 sm:h-5 w-auto"
            />
            <div className="flex items-center gap-2">
              {match.status === "live" ? (
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-hockey-live animate-pulse-live" />
                  <span className="text-[10px] sm:text-[11px] font-bold text-hockey-live tracking-wider">LIVE</span>
                </div>
              ) : match.status === "pre_game" ? (
                <span className="text-[10px] sm:text-[11px] font-medium text-hockey-text-muted tabular-nums">{countdown}</span>
              ) : (
                <span className="text-[10px] sm:text-[11px] font-medium text-hockey-text-muted">Завершён</span>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between gap-2 sm:gap-3">
            <div className="flex-1 flex items-center justify-end gap-2 sm:gap-3">
              <p className="text-sm sm:text-base font-bold leading-tight text-right">{match.team_home}</p>
              {showLogos && getTeamLogo(match.team_home) && (
                <img src={getTeamLogo(match.team_home)!} alt={match.team_home} className="w-8 h-8 sm:w-10 sm:h-10 object-contain" />
              )}
            </div>
            <div className="flex-shrink-0 px-1 sm:px-2">
              {match.status === "finished" && score ? (
                <span className="flex flex-col items-center leading-none">
                  <span className="text-base sm:text-xl font-black tabular-nums whitespace-nowrap">{score}</span>
                  {finish === "ot" && (
                    <span className="text-[9px] sm:text-[10px] font-bold text-hockey-text-muted mt-0.5">ОТ</span>
                  )}
                  {finish === "so" && (
                    <span className="text-[9px] sm:text-[10px] font-bold text-hockey-text-muted mt-0.5">Б</span>
                  )}
                </span>
              ) : (
                <span className="text-[10px] sm:text-xs font-black text-hockey-text-muted">VS</span>
              )}
            </div>
            <div className="flex-1 flex items-center gap-2 sm:gap-3">
              {showLogos && getTeamLogo(match.team_away) && (
                <img src={getTeamLogo(match.team_away)!} alt={match.team_away} className="w-8 h-8 sm:w-10 sm:h-10 object-contain" />
              )}
              <p className="text-sm sm:text-base font-bold leading-tight text-left">{match.team_away}</p>
            </div>
          </div>

          <div className="mt-3 sm:mt-4 flex items-center justify-between">
            <span className="text-[10px] sm:text-xs text-hockey-text-secondary">
              {parseMatchDate(match.datetime_utc).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
            </span>
            {match.status === "pre_game" ? (
              <RemindButton />
            ) : (
              <span className={`text-[10px] sm:text-xs font-bold px-2 sm:px-3 py-1 sm:py-1.5 rounded-lg transition-all duration-200 ${
                featured
                  ? "bg-hockey-accent text-white"
                  : "bg-white/5 text-hockey-text-secondary group-hover:bg-hockey-accent group-hover:text-white"
              }`}>
                {match.status === "live" ? "Смотреть" : match.status === "finished" ? "Смотреть статистику" : "Посмотреть запись"}
              </span>
            )}
          </div>
        </div>
      </div>
    </Link>
  );
}
