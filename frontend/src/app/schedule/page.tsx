"use client";

import { useEffect, useState, useMemo } from "react";
import MatchCard from "@/components/MatchCard";
import KhlMatchCard, { mskToLocal } from "@/components/KhlMatchCard";
import { parseMatchDate } from "@/lib/parse-date";
import { localDateKey, tzOffsetMinutes } from "@/lib/local-date";
import DateSelector from "@/components/DateSelector";
import TeamSearch from "@/components/TeamSearch";
import FavoritesFilter from "@/components/FavoritesFilter";
import TeamMatches from "@/components/TeamMatches";
import { useFavorites } from "@/lib/FavoritesContext";
import { getTeamLogo } from "@/lib/team-logos";
import { useKhlCalendar } from "@/lib/khl-calendar";
import {
  ScoreResult,
  buildResultsMap,
  pairKey,
  scoreFor,
  eventIdFor,
} from "@/lib/match-scores";

const LEAGUES = [
  { id: "KHL", label: "КХЛ", logo: "/KHL.svg" },
  { id: "VHL", label: "ВХЛ", logo: "/VHL.svg" },
  { id: "MHL", label: "МХЛ", logo: "/MHL.svg" },
  { id: "NHL", label: "НХЛ", logo: "/NHL.svg" },
] as const;

type LeagueId = (typeof LEAGUES)[number]["id"];

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

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
  current_period?: string | null;
}

export default function SchedulePage() {
  const [selectedDate, setSelectedDate] = useState(localDateKey());
  const [league, setLeague] = useState<LeagueId>("KHL");
  const [searchedTeam, setSearchedTeam] = useState("");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [apiMatches, setApiMatches] = useState<Match[]>([]);
  const [results, setResults] = useState<Record<string, ScoreResult>>({});
  const [loading, setLoading] = useState(true);
  const { favorites, toggle } = useFavorites();
  const { matches: khlCalendarMatches } = useKhlCalendar();

  const selectLeague = (l: LeagueId) => {
    setLeague(l);
    setSearchedTeam("");
    setSelectedDate(localDateKey());
  };

  useEffect(() => {
    if (favoritesOnly && favorites.length === 0) {
      setFavoritesOnly(false);
    }
  }, [favorites, favoritesOnly]);

  useEffect(() => {
    if (league === "VHL") {
      setApiMatches([]);
      setResults({});
      setLoading(false);
      return;
    }
    setLoading(true);
    fetch(`${API_URL}/api/schedule?date=${selectedDate}&league=${league}&tz_offset=${tzOffsetMinutes()}`)
      .then((r) => r.json())
      .then((data) => setApiMatches(Array.isArray(data) ? data : []))
      .catch(() => setApiMatches([]))
      .finally(() => setLoading(false));

    let cancelled = false;
    const loadResults = () => {
      if (league !== "KHL") {
        setResults({});
        return;
      }
      fetch(`${API_URL}/api/results?date=${selectedDate}&league=KHL`)
        .then((r) => (r.ok ? r.json() : null))
        .then((json) => {
          if (cancelled || !json?.results) return;
          setResults(buildResultsMap(json.results as ScoreResult[]));
        })
        .catch(() => {});
    };
    loadResults();
    const timer = setInterval(loadResults, 5 * 60 * 1000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [selectedDate, league]);

  // WebSocket: обновляем счёт в реальном времени
  useEffect(() => {
    if (league === "VHL") return;
    const wsUrl = API_URL.replace(/^https/, "wss").replace(/^http/, "ws") + "/ws";
    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket(wsUrl);
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.type === "matches_update" && Array.isArray(msg.data)) {
            const updates = (msg.data as Match[]).filter((u) => u.league === league);
            setApiMatches((prev) => {
              const map = new Map(prev.map((m) => [m.id, m]));
              for (const u of updates) map.set(u.id, u);
              return Array.from(map.values());
            });
            setResults((prev) => {
              const next = { ...prev };
              for (const u of updates) {
                const pk = pairKey(u.team_home, u.team_away);
                const finish =
                  u.current_period === "Овертайм"
                    ? "ot"
                    : u.current_period === "Буллиты"
                      ? "so"
                      : "reg";
                next[pk] = {
                  home: u.team_home,
                  away: u.team_away,
                  score_home: u.home_score ?? 0,
                  score_away: u.away_score ?? 0,
                  finish: finish as "reg" | "ot" | "so",
                };
              }
              return next;
            });
          }
        } catch {}
      };
      ws.onerror = () => {
        ws?.close();
      };
    } catch {}
    return () => {
      ws?.close();
    };
  }, [league]);

  const khlMatches = useMemo(() => {
    if (league !== "KHL") return [];
    return khlCalendarMatches
      .filter((m) => localDateKey(mskToLocal(m.date, m.time)) === selectedDate)
      .sort((a, b) => a.time.localeCompare(b.time));
  }, [selectedDate, league, khlCalendarMatches]);

  const filteredApi = apiMatches;

  const allTeams = useMemo(() => {
    const teams = new Set<string>();
    if (league === "KHL") {
      const KHL_TEAMS = [
        "Авангард", "Адмирал", "Ак Барс", "Амур", "Автомобилист",
        "Барыс", "Лада", "Локомотив", "Металлург Мг", "Нефтехимик",
        "Салават Юлаев", "Северсталь", "СКА", "Сибирь", "Спартак",
        "Торпедо", "Трактор", "ЦСКА", "Динамо М", "Динамо Мн",
        "ХК Сочи", "Шанхайские Драконы",
      ];
      KHL_TEAMS.forEach((t) => teams.add(t));
    }
    apiMatches.forEach((m) => { if (m.team_home) teams.add(m.team_home); if (m.team_away) teams.add(m.team_away); });
    khlMatches.forEach((m) => { teams.add(m.home); teams.add(m.away); });
    return Array.from(teams).sort();
  }, [apiMatches, khlMatches, league]);

  const finalApi = useMemo(() => {
    let result = filteredApi;
    if (searchedTeam) {
      const q = searchedTeam.toLowerCase();
      result = result.filter((m) => m.team_home.toLowerCase().includes(q) || m.team_away.toLowerCase().includes(q));
    }
    if (favoritesOnly && favorites.length > 0) {
      result = result.filter((m) => favorites.includes(m.team_home) || favorites.includes(m.team_away));
    }
    return result;
  }, [filteredApi, searchedTeam, favoritesOnly, favorites]);

  const finalKhl = useMemo(() => {
    const apiTeamPairs = new Set(
      apiMatches.map((m) => `${m.team_home}|${m.team_away}`)
    );
    let result = khlMatches.filter(
      (m) => !apiTeamPairs.has(`${m.home}|${m.away}`) && !apiTeamPairs.has(`${m.away}|${m.home}`)
    );
    if (searchedTeam) {
      result = result.filter((m) => m.home === searchedTeam || m.away === searchedTeam);
    }
    if (favoritesOnly && favorites.length > 0) {
      result = result.filter((m) => favorites.includes(m.home) || favorites.includes(m.away));
    }
    return result;
  }, [khlMatches, apiMatches, searchedTeam, favoritesOnly, favorites]);

  const apiByTime: Record<string, Match[]> = finalApi.reduce((acc, m) => {
    const t = parseMatchDate(m.datetime_utc).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    if (!acc[t]) acc[t] = [];
    acc[t].push(m);
    return acc;
  }, {} as Record<string, Match[]>);

  const khlByTime: Record<string, typeof finalKhl> = finalKhl.reduce((acc, m) => {
    const [h, min] = m.time.split(":").map(Number);
    const utcMs = Date.UTC(
      parseInt(m.date.slice(0, 4)),
      parseInt(m.date.slice(5, 7)) - 1,
      parseInt(m.date.slice(8, 10)),
      h, min, 0
    ) - 3 * 60 * 60 * 1000;
    const localTime = new Date(utcMs).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
    if (!acc[localTime]) acc[localTime] = [];
    acc[localTime].push(m);
    return acc;
  }, {} as Record<string, typeof finalKhl>);

  const allTimes = [...new Set([...Object.keys(apiByTime), ...Object.keys(khlByTime)])].sort();

  const hasAnyMatches = allTimes.length > 0;

  const showTeamSearch = searchedTeam || favoritesOnly;

  return (
    <div className="pt-20 sm:pt-24 pb-8 sm:pb-16">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8">
        <h1 className="text-2xl sm:text-3xl font-black tracking-tight uppercase mb-4 sm:mb-6">Календарь</h1>

        <DateSelector selected={selectedDate} onSelect={setSelectedDate} />

        <div className="flex gap-2 mt-3 sm:mt-4">
          {LEAGUES.map((l) => (
            <button
              key={l.id}
              onClick={() => selectLeague(l.id)}
              title={l.label}
              aria-label={l.label}
              className={`px-3 py-1.5 rounded-lg transition-all flex items-center justify-center ${
                league === l.id
                  ? "bg-hockey-accent/10 border-2 border-hockey-accent shadow-lg shadow-hockey-accent/20"
                  : "bg-hockey-card border border-hockey-border hover:border-hockey-border-light opacity-60 hover:opacity-100"
              }`}
            >
              <img src={l.logo} alt={l.label} className="h-4 sm:h-5 w-auto" />
            </button>
          ))}
        </div>

        <div className="flex flex-col sm:flex-row gap-3 mb-6 sm:mb-8 mt-4 sm:mt-6">
          <TeamSearch teams={allTeams} onSelect={setSearchedTeam} />
          <FavoritesFilter active={favoritesOnly} onToggle={() => { setFavoritesOnly(!favoritesOnly); setSearchedTeam(""); }} />
        </div>

        {league === "VHL" ? (
          <div className="glass rounded-2xl p-6 sm:p-12 text-center">
            <p className="text-hockey-text-secondary text-base sm:text-lg">
              Календарь ВХЛ скоро появится
            </p>
          </div>
        ) : showTeamSearch ? (
          <div className="glass rounded-2xl p-4 sm:p-6">
            {searchedTeam ? (
              <TeamMatches teams={[searchedTeam]} title={`Матчи: ${searchedTeam}`} />
            ) : favoritesOnly && favorites.length > 0 ? (
              <>
                <div className="flex flex-wrap gap-2 mb-4">
                  {favorites.map((team) => (
                    <span key={team} className="inline-flex items-center gap-1.5 px-2 py-1.5 rounded-lg bg-hockey-accent/10 border border-hockey-accent/30">
                      {getTeamLogo(team) && (
                        <img src={getTeamLogo(team)!} alt={team} className="w-6 h-6 object-contain" />
                      )}
                      <button
                        onClick={() => toggle(team)}
                        className="p-0.5 rounded hover:bg-hockey-accent/20 transition-colors text-hockey-accent"
                        title="Убрать из избранного"
                      >
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="18" y1="6" x2="6" y2="18" />
                          <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                      </button>
                    </span>
                  ))}
                </div>
                <TeamMatches teams={favorites} />
              </>
            ) : favoritesOnly ? (
              <div className="text-center py-8">
                <p className="text-hockey-text-secondary text-sm">Добавьте команды в избранное на карточках календаря</p>
              </div>
            ) : null}
          </div>
        ) : loading ? (
          <div className="space-y-3 sm:space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-20 sm:h-24 bg-hockey-card rounded-xl animate-pulse" />
            ))}
          </div>
        ) : !hasAnyMatches ? (
          <div className="glass rounded-2xl p-6 sm:p-12 text-center">
            <p className="text-hockey-text-secondary text-base sm:text-lg">Нет матчей на выбранный день</p>
          </div>
        ) : (
          <div className="space-y-5 sm:space-y-8">
            {allTimes.map((time) => {
              const timeApiMatches = apiByTime[time] || [];
              const timeKhlMatches = khlByTime[time] || [];

              return (
                <div key={time}>
                  <div className="flex items-center gap-2 sm:gap-3 mb-3 sm:mb-4">
                    <span className="text-xs sm:text-sm font-bold text-hockey-accent tabular-nums">{time}</span>
                    <div className="flex-1 h-px bg-hockey-border" />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4">
                    {timeApiMatches.map((match) => {
                      const s = scoreFor(results, match.team_home, match.team_away);
                      return (
                        <MatchCard key={match.id} match={match} score={s?.text ?? null} finish={s?.finish ?? null} />
                      );
                    })}
                    {timeKhlMatches.map((match, i) => {
                      const s = scoreFor(results, match.home, match.away);
                      const eid = eventIdFor(results, match.home, match.away) ?? match.id ?? null;
                      return (
                        <KhlMatchCard
                          key={`khl-${time}-${i}`}
                          date={match.date}
                          time={match.time}
                          home={match.home}
                          away={match.away}
                          score={s?.text ?? null}
                          finish={s?.finish ?? null}
                          home_score={match.score_home ?? null}
                          away_score={match.score_away ?? null}
                          event_id={eid}
                        />
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
