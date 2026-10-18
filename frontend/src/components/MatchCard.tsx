"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getTeamLogo } from "@/lib/team-logos";
import { parseMatchDate } from "@/lib/parse-date";
import RemindButton from "@/components/RemindButton";
import { useScoreToggle } from "@/context/ScoreToggleContext";
import { useFavorites } from "@/lib/FavoritesContext";

interface Match {
  id: number;
  match_uid: string;
  league: string;
  team_home: string;
  team_away: string;
  datetime_utc: string;
  status: string;
  stream_urls: { url: string; quality: string; source: string }[];
  home_score?: number | null;
  away_score?: number | null;
  current_period?: string | null;
}

function teamNameClass(name: string): string {
  if (name === "Автомобилист") return "text-[6.5pt] sm:text-[8pt]";
  return name.length > 12 ? "text-[13px] sm:text-[15px]" : "text-sm sm:text-base";
}

export default function MatchCard({ match, featured = false, score = null, finish = null }: { match: Match; featured?: boolean; score?: string | null; finish?: string | null }) {
  const [countdown, setCountdown] = useState("");
  const { showScores } = useScoreToggle();
  const { isFavorite } = useFavorites();

  const favHome = match.status === "live" && isFavorite(match.team_home);
  const favAway = match.status === "live" && isFavorite(match.team_away);
  const favoriteLive = favHome || favAway;

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
    <Link href={`/${match.league.toLowerCase()}/match/${match.id}`}>
      <div
        className={`group relative rounded-xl overflow-hidden transition-all duration-300 card-hover ${
          favoriteLive
            ? "bg-hockey-accent/15 border-2 border-hockey-accent/60 animate-glow-fav"
            : featured
              ? "bg-hockey-accent/10 border border-hockey-accent/30 animate-glow-red"
              : "bg-hockey-card border border-hockey-border hover:border-hockey-border-light"
        }`}
      >
        <div className="absolute inset-0 bg-gradient-to-r from-hockey-accent/0 via-hockey-accent/[0.02] to-hockey-accent/0 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />

        {favoriteLive && (
          <>
            <span className="bg-ice-particle absolute left-[12%] bottom-3 w-1.5 h-1.5 rounded-full" style={{ animationDelay: "0s" }} />
            <span className="bg-ice-particle absolute left-[47%] bottom-4 w-1 h-1 rounded-full" style={{ animationDelay: "1.4s" }} />
            <span className="bg-ice-particle absolute left-[83%] bottom-3 w-1.5 h-1.5 rounded-full" style={{ animationDelay: "2.8s" }} />
          </>
        )}

        <div className="relative p-3 sm:p-5">
          <div className="flex items-center justify-between mb-3 sm:mb-4">
            <div className="flex items-center gap-2 min-w-0">
              <img
                src={`/${match.league}.svg`}
                alt={match.league}
                className="h-4 sm:h-5 w-auto"
              />
              {favoriteLive && (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-hockey-accent/20 border border-hockey-accent/40 text-[9px] sm:text-[10px] font-bold uppercase tracking-wider text-hockey-accent">
                  <svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                  </svg>
                  Моя команда
                </span>
              )}
            </div>
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
              <p className={`font-bold leading-tight text-right ${teamNameClass(match.team_home)} ${favHome ? "text-hockey-accent" : ""}`}>{match.team_home}</p>
              {getTeamLogo(match.team_home) && (
                <img src={getTeamLogo(match.team_home)!} alt={match.team_home} className="w-8 h-8 sm:w-10 sm:h-10 object-contain" />
              )}
            </div>
            <div className="flex-shrink-0 px-1 sm:px-2">
              {showScores ? (
                match.status === "finished" &&
                (score || (match.home_score != null && match.away_score != null)) ? (
                  <span className="flex flex-col items-center leading-none">
                    <span className="text-base sm:text-xl font-black tabular-nums whitespace-nowrap">
                      {score ?? `${match.home_score} : ${match.away_score}`}
                    </span>
                    {finish === "ot" && (
                      <span className="text-[9px] sm:text-[10px] font-bold text-hockey-text-muted mt-0.5">ОТ</span>
                    )}
                    {finish === "so" && (
                      <span className="text-[9px] sm:text-[10px] font-bold text-hockey-text-muted mt-0.5">Б</span>
                    )}
                  </span>
                ) : match.status === "live" && match.home_score != null && match.away_score != null ? (
                  <span className="flex flex-col items-center leading-none">
                    <span className="text-base sm:text-xl font-black tabular-nums whitespace-nowrap">{match.home_score} : {match.away_score}</span>
                    {match.current_period && (
                      <span className="text-[9px] sm:text-[10px] font-bold text-hockey-live mt-0.5">{match.current_period}</span>
                    )}
                  </span>
                ) : (
                  <span className="text-[10px] sm:text-xs font-black text-hockey-text-muted">VS</span>
                )
              ) : (
                <span className="text-[10px] sm:text-xs text-hockey-text-muted">{match.current_period ?? "VS"}</span>
              )}
            </div>
            <div className="flex-1 flex items-center gap-2 sm:gap-3">
              {getTeamLogo(match.team_away) && (
                <img src={getTeamLogo(match.team_away)!} alt={match.team_away} className="w-8 h-8 sm:w-10 sm:h-10 object-contain" />
              )}
              <p className={`font-bold leading-tight text-left ${teamNameClass(match.team_away)} ${favAway ? "text-hockey-accent" : ""}`}>{match.team_away}</p>
            </div>
          </div>

          <div className="mt-3 sm:mt-4 flex items-center justify-between">
            <span className="text-[10px] sm:text-xs text-hockey-text-secondary">
              {parseMatchDate(match.datetime_utc).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
            </span>
            {match.status === "pre_game" ? (
              <RemindButton
                league={match.league}
                teamHome={match.team_home}
                teamAway={match.team_away}
                matchId={match.id}
                datetimeUtc={match.datetime_utc}
              />
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
