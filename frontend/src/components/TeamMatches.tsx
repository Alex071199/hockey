"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import { getTeamLogo } from "@/lib/team-logos";
import { useKhlCalendar, KhlCalendarMatch } from "@/lib/khl-calendar";
import { parseMatchDate } from "@/lib/parse-date";
import { mskToLocal, getKhlStatus } from "@/components/KhlMatchCard";
import {
  ScoreResult,
  buildResultsMap,
  finishLabel,
  scoreFor,
} from "@/lib/match-scores";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface ApiMatch {
  id: number;
  league: string;
  team_home: string;
  team_away: string;
  datetime_utc: string;
  status: string;
  home_score?: number | null;
  away_score?: number | null;
}

interface TeamMatchesProps {
  teams: string[];
  title?: string;
}

function formatMonth(year: number, month: number): string {
  const months = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
  return `${months[month - 1]} ${year}`;
}

function getDateKey(d: string): string {
  return (d || "").split("T")[0];
}

function pad(n: number): string {
  return n.toString().padStart(2, "0");
}

// Локальная дата (YYYY-MM-DD в часовом поясе браузера) для группировки
function localDateKey(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function localTime(d: Date): string {
  return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

export default function TeamMatches({ teams, title }: TeamMatchesProps) {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [apiMatches, setApiMatches] = useState<ApiMatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [scores, setScores] = useState<Record<string, Record<string, ScoreResult>>>({});
  const fetchedDates = useRef<Set<string>>(new Set());

  const monthStr = `${year}-${month.toString().padStart(2, "0")}`;

  useEffect(() => {
    if (teams.length === 0) return;
    setLoading(true);

    const promises = teams.map((team) =>
      fetch(`${API_URL}/api/schedule/team/${encodeURIComponent(team)}?month=${monthStr}`)
        .then((r) => (r.ok ? r.json() : []))
        .catch(() => [])
    );

    Promise.all(promises).then((results) => {
      const all = results.flat().filter((m) => m && typeof m.id !== "undefined" && m.datetime_utc);
      const unique = all.filter((m: ApiMatch, i: number, arr: ApiMatch[]) =>
        arr.findIndex((x) => x.id === m.id) === i
      );
      setApiMatches(unique);
      setLoading(false);
    });
  }, [teams, monthStr]);

  const { matches: calendarMatches } = useKhlCalendar();

  const khlMatches = useMemo(() => {
    return calendarMatches.filter((m) => {
      const d = new Date(m.date + "T00:00:00");
      return d.getFullYear() === year && d.getMonth() + 1 === month &&
        teams.some((t) => m.home === t || m.away === t);
    });
  }, [teams, year, month, calendarMatches]);

  const allMatches = useMemo(() => {
    const apiByDate: Record<string, { type: "api"; match: ApiMatch }[]> = {};
    apiMatches.forEach((m) => {
      if (!m.datetime_utc) return;
      const key = localDateKey(parseMatchDate(m.datetime_utc));
      if (!apiByDate[key]) apiByDate[key] = [];
      apiByDate[key].push({ type: "api", match: m });
    });

    const khlByDate: Record<string, { type: "khl"; match: KhlCalendarMatch }[]> = {};
    khlMatches.forEach((m) => {
      const key = localDateKey(mskToLocal(m.date, m.time));
      if (!khlByDate[key]) khlByDate[key] = [];
      khlByDate[key].push({ type: "khl", match: m });
    });

    const allDates = new Set([...Object.keys(apiByDate), ...Object.keys(khlByDate)]);
    return Array.from(allDates)
      .sort()
      .map((date) => {
        const apiList = apiByDate[date] || [];
        // Убираем дубли: статический матч, уже покрытый API-матчем
        const apiPairs = new Set(
          apiList.flatMap((item) => [
            `${item.match.team_home}|${item.match.team_away}`,
            `${item.match.team_away}|${item.match.team_home}`,
          ])
        );
        const khlList = (khlByDate[date] || []).filter(
          (item) =>
            !apiPairs.has(`${item.match.home}|${item.match.away}`) &&
            !apiPairs.has(`${item.match.away}|${item.match.home}`)
        );
        return { date, matches: [...apiList, ...khlList] };
      })
      .filter((g) => g.matches.length > 0);
  }, [apiMatches, khlMatches]);

  // Счёт завершённых матчей: тянем результаты по датам (только прошедшие,
  // чтобы не жечь квоту API на будущих датах)
  useEffect(() => {
    const d = new Date();
    const todayStr = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    const dates = [...new Set(allMatches.map((g) => g.date))].filter(
      (dt) => dt <= todayStr && !fetchedDates.current.has(dt)
    );
    if (dates.length === 0) return;
    let cancelled = false;
    Promise.all(
      dates.map((dt) =>
        fetch(`${API_URL}/api/results?date=${dt}&league=KHL`)
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null)
      )
    ).then((payloads) => {
      if (cancelled) return;
      setScores((prev) => {
        const next = { ...prev };
        payloads.forEach((p, i) => {
          // Помечаем дату загруженной только по факту успеха,
          // иначе повторный проход эффекта (StrictMode) пропустит её навсегда
          if (p?.results) {
            next[dates[i]] = buildResultsMap(p.results as ScoreResult[]);
            fetchedDates.current.add(dates[i]);
          }
        });
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [allMatches]);

  const hasPrev = !(year === now.getFullYear() && month === now.getMonth() + 1);

  function prevMonth() {
    if (month === 1) { setMonth(12); setYear(year - 1); }
    else setMonth(month - 1);
  }

  function nextMonth() {
    if (month === 12) { setMonth(1); setYear(year + 1); }
    else setMonth(month + 1);
  }

  if (teams.length === 0) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base sm:text-lg font-bold text-white">
          {title || teams.join(", ")}
        </h3>
        <span className="text-xs sm:text-sm text-hockey-text-secondary font-medium">
          {formatMonth(year, month)}
        </span>
      </div>

      <div className="flex items-center gap-2">
        {hasPrev && (
          <button
            onClick={prevMonth}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-hockey-card border border-hockey-border text-hockey-text-secondary hover:text-white hover:border-hockey-border-light transition-all"
          >
            &larr; Назад
          </button>
        )}
        <button
          onClick={nextMonth}
          className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-hockey-card border border-hockey-border text-hockey-text-secondary hover:text-white hover:border-hockey-border-light transition-all"
        >
          {formatMonth(month === 12 ? year + 1 : year, month === 12 ? 1 : month + 1)} &rarr;
        </button>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-hockey-card rounded-xl animate-pulse" />
          ))}
        </div>
      ) : allMatches.length === 0 ? (
        <div className="glass rounded-xl p-6 text-center">
          <p className="text-sm text-hockey-text-secondary">Нет матчей в этом месяце</p>
        </div>
      ) : (
        <div className="space-y-4">
          {allMatches.map(({ date, matches }) => (
            <div key={date}>
              <div className="text-xs font-bold text-hockey-accent mb-2 uppercase">
                {new Date(date + "T00:00:00").toLocaleDateString("ru-RU", { day: "numeric", month: "long", weekday: "short" })}
              </div>
              <div className="space-y-2">
                {matches.map((item, i) => {
                  if (item.type === "api") {
                    const m = item.match;
                    const done = m.status === "finished";
                    const s = done ? scoreFor(scores[date] ?? {}, m.team_home, m.team_away) : null;
                    const fl = s ? finishLabel(s.finish) : null;
                    return (
                      <div key={`api-${m.id}`} className="flex items-center gap-3 p-3 rounded-xl bg-hockey-card border border-hockey-border">
                        <img src={`/${m.league}.svg`} alt={m.league} className="h-4 w-auto flex-shrink-0" />
                        <div className="flex-1 flex items-center gap-2 min-w-0">
                          <div className="flex items-center gap-1.5 flex-1 justify-end min-w-0">
                            <span className="text-xs sm:text-sm font-bold text-right truncate">{m.team_home}</span>
                            {m.league === "KHL" && getTeamLogo(m.team_home) && (
                              <img src={getTeamLogo(m.team_home)!} alt="" className="w-5 h-5 object-contain flex-shrink-0" />
                            )}
                          </div>
                          {s ? (
                            <span className="flex flex-col items-center leading-none flex-shrink-0">
                              <span className="text-sm font-black tabular-nums whitespace-nowrap">{s.text}</span>
                              {fl && <span className="text-[9px] font-bold text-hockey-text-muted mt-0.5">{fl}</span>}
                            </span>
                          ) : done && m.home_score != null && m.away_score != null ? (
                            <span className="text-sm font-black tabular-nums whitespace-nowrap flex-shrink-0">
                              {m.home_score} : {m.away_score}
                            </span>
                          ) : (
                            <span className="text-[10px] font-black text-hockey-text-muted flex-shrink-0">VS</span>
                          )}
                          <div className="flex-1 flex items-center gap-1.5 min-w-0">
                            {m.league === "KHL" && getTeamLogo(m.team_away) && (
                              <img src={getTeamLogo(m.team_away)!} alt="" className="w-5 h-5 object-contain flex-shrink-0" />
                            )}
                            <span className="text-xs sm:text-sm font-bold text-left truncate">{m.team_away}</span>
                          </div>
                        </div>
                        <span className="text-[10px] sm:text-xs text-hockey-text-secondary flex-shrink-0">
                          {done
                            ? "Завершён"
                            : parseMatchDate(m.datetime_utc).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
                        </span>
                      </div>
                    );
                  } else {
                    const m = item.match;
                    const done = m.status === "finished" || getKhlStatus(m.date, m.time) === "finished";
                    const s = done ? scoreFor(scores[date] ?? {}, m.home, m.away) : null;
                    const fl = s ? finishLabel(s.finish) : null;
                    const calScore =
                      !s && done && m.score_home != null && m.score_away != null
                        ? `${m.score_home} : ${m.score_away}`
                        : null;
                    return (
                      <div key={`khl-${date}-${i}`} className="flex items-center gap-3 p-3 rounded-xl bg-hockey-card border border-hockey-border">
                        <img src="/KHL.svg" alt="КХЛ" className="h-4 w-auto flex-shrink-0" />
                        <div className="flex-1 flex items-center gap-2 min-w-0">
                          <div className="flex items-center gap-1.5 flex-1 justify-end min-w-0">
                            <span className="text-xs sm:text-sm font-bold text-right truncate">{m.home}</span>
                            {getTeamLogo(m.home) && (
                              <img src={getTeamLogo(m.home)!} alt="" className="w-5 h-5 object-contain flex-shrink-0" />
                            )}
                          </div>
                          {s ? (
                            <span className="flex flex-col items-center leading-none flex-shrink-0">
                              <span className="text-sm font-black tabular-nums whitespace-nowrap">{s.text}</span>
                              {fl && <span className="text-[9px] font-bold text-hockey-text-muted mt-0.5">{fl}</span>}
                            </span>
                          ) : calScore ? (
                            <span className="text-sm font-black tabular-nums whitespace-nowrap flex-shrink-0">
                              {calScore}
                            </span>
                          ) : (
                            <span className="text-[10px] font-black text-hockey-text-muted flex-shrink-0">VS</span>
                          )}
                          <div className="flex-1 flex items-center gap-1.5 min-w-0">
                            {getTeamLogo(m.away) && (
                              <img src={getTeamLogo(m.away)!} alt="" className="w-5 h-5 object-contain flex-shrink-0" />
                            )}
                            <span className="text-xs sm:text-sm font-bold text-left truncate">{m.away}</span>
                          </div>
                        </div>
                        <span className="text-[10px] sm:text-xs text-hockey-text-secondary flex-shrink-0">
                          {done ? "Завершён" : m.time ? localTime(mskToLocal(m.date, m.time)) : m.time}
                        </span>
                      </div>
                    );
                  }
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
