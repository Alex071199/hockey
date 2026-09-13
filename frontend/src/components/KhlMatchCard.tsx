"use client";

import { useEffect, useState } from "react";
import { getTeamLogo } from "@/lib/team-logos";
import { useFavorites } from "@/lib/FavoritesContext";
import RemindButton from "@/components/RemindButton";

function StarButton({ team }: { team: string }) {
  const { toggle, isFavorite } = useFavorites();
  const fav = isFavorite(team);
  return (
    <button
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggle(team); }}
      className="p-0.5 rounded hover:bg-white/10 transition-colors flex-shrink-0"
      title={fav ? "Убрать из избранного" : "В избранное"}
    >
      <svg width="12" height="12" viewBox="0 0 24 24" fill={fav ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2.5" className={fav ? "text-hockey-accent" : "text-hockey-text-muted hover:text-hockey-accent"}>
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
      </svg>
    </button>
  );
}

export type KhlStatus = "upcoming" | "live" | "finished";

export function getKhlStatus(date: string, time: string): KhlStatus {
  const [h, m] = time.split(":").map(Number);
  const utcMs =
    Date.UTC(
      parseInt(date.slice(0, 4)),
      parseInt(date.slice(5, 7)) - 1,
      parseInt(date.slice(8, 10)),
      h,
      m,
      0
    ) -
    3 * 60 * 60 * 1000;
  const matchTime = new Date(utcMs);
  const now = new Date();
  const diff = matchTime.getTime() - now.getTime();
  if (diff < -120 * 60 * 1000) return "finished";
  if (diff < 0) return "live";
  return "upcoming";
}

function mskTimeToLocal(date: string, time: string): string {
  return mskToLocal(date, time).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

export function mskToLocal(date: string, time: string): Date {
  const [h, m] = time.split(":").map(Number);
  const utcMs =
    Date.UTC(
      parseInt(date.slice(0, 4)),
      parseInt(date.slice(5, 7)) - 1,
      parseInt(date.slice(8, 10)),
      h,
      m,
      0
    ) -
    3 * 60 * 60 * 1000;
  return new Date(utcMs);
}

interface KhlMatchCardProps {
  date: string;
  time: string;
  home: string;
  away: string;
  score?: string | null;
  finish?: string | null;
  hideLive?: boolean;
}

export default function KhlMatchCard({ date, time, home, away, score = null, finish = null, hideLive = false }: KhlMatchCardProps) {
  const [status, setStatus] = useState<"upcoming" | "live" | "finished">("upcoming");

  useEffect(() => {
    function checkStatus() {
      setStatus(getKhlStatus(date, time));
    }
    checkStatus();
    const id = setInterval(checkStatus, 30000);
    return () => clearInterval(id);
  }, [date, time]);

  if (hideLive && status === "live") return null;

  return (
    <div className="group relative rounded-xl overflow-hidden transition-all duration-300 bg-hockey-card border border-hockey-border hover:border-hockey-border-light card-hover">
      <div className="absolute inset-0 bg-gradient-to-r from-hockey-accent/0 via-hockey-accent/[0.02] to-hockey-accent/0 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />

      <div className="relative p-3 sm:p-5">
        <div className="flex items-center justify-between mb-3 sm:mb-4">
            <img
              src="/KHL.svg"
              alt="КХЛ"
              className="h-4 sm:h-5 w-auto"
            />
          {status === "live" ? (
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-hockey-live animate-pulse-live" />
              <span className="text-[10px] sm:text-[11px] font-bold text-hockey-live tracking-wider">LIVE</span>
            </div>
          ) : status === "finished" ? (
            <span className="text-[10px] sm:text-[11px] font-medium text-hockey-text-muted">Завершён</span>
          ) : null}
        </div>

        <div className="flex items-center justify-between gap-2 sm:gap-3">
          <div className="flex-1 flex items-center justify-end gap-1.5 sm:gap-2">
            <p className="text-sm sm:text-base font-bold leading-tight text-right">{home}</p>
            <StarButton team={home} />
            {getTeamLogo(home) && (
              <img src={getTeamLogo(home)!} alt={home} className="w-8 h-8 sm:w-10 sm:h-10 object-contain" />
            )}
          </div>
          <div className="flex-shrink-0 px-1 sm:px-2">
            {status === "finished" && score ? (
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
          <div className="flex-1 flex items-center gap-1.5 sm:gap-2">
            {getTeamLogo(away) && (
              <img src={getTeamLogo(away)!} alt={away} className="w-8 h-8 sm:w-10 sm:h-10 object-contain" />
            )}
            <StarButton team={away} />
            <p className="text-sm sm:text-base font-bold leading-tight text-left">{away}</p>
          </div>
        </div>

        <div className="mt-3 sm:mt-4 flex items-center justify-between">
          {status === "live" ? (
            <span className="text-[10px] sm:text-xs text-hockey-live font-bold">Сейчас играется</span>
          ) : (
            <span className="text-[10px] sm:text-xs text-hockey-text-secondary">{mskTimeToLocal(date, time)}</span>
          )}

          {status === "live" ? (
            <span className="text-[10px] sm:text-xs font-bold px-2 sm:px-3 py-1 sm:py-1.5 rounded-lg bg-hockey-accent text-white animate-glow-red">
              Смотреть
            </span>
          ) : status === "finished" ? (
            <span className="text-[10px] sm:text-xs font-bold px-2 sm:px-3 py-1 sm:py-1.5 rounded-lg bg-white/5 text-hockey-text-muted">
              Смотреть статистику
            </span>
          ) : (
            <RemindButton />
          )}
        </div>
      </div>
    </div>
  );
}
