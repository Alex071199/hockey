"use client";

import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { parseMatchDate } from "@/lib/parse-date";
import StreamPlayer from "@/components/StreamPlayer";
import PlayerGate from "@/components/PlayerGate";
import MatchStats, { MatchStatsData } from "@/components/MatchStats";
import DonateButtons from "@/components/DonateButtons";
import DonationRain from "@/components/DonationRain";
import { fetchSportPlusTVStreams, Stream } from "@/lib/sportplustv";
import { findWinBroadcast, winStream } from "@/lib/winbroadcast";
import { getTeamLogo } from "@/lib/team-logos";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

// Гейт перед плеером: после клика «Смотреть» (или успешного доната)
// не показываем его снова в течение суток.
const GATE_KEY = "hockey_gate_seen_at";
const GATE_TTL_MS = 24 * 60 * 60 * 1000;

function gateAlreadySeen(): boolean {
  try {
    const ts = Number(localStorage.getItem(GATE_KEY) || 0);
    return ts > 0 && Date.now() - ts < GATE_TTL_MS;
  } catch {
    return false;
  }
}

function markGateSeen(): void {
  try {
    localStorage.setItem(GATE_KEY, String(Date.now()));
  } catch {}
}

interface Match {
  id: number; match_uid: string; league: string;
  team_home: string; team_away: string; datetime_utc: string;
  status: string; stream_urls: Stream[];
  home_score: number | null; away_score: number | null;
  current_period: string | null;
  sp_match_id?: number | null;
}

function isAceStream(s: Stream) {
  return s.source === "acestream" || s.url.startsWith("acestream://");
}

function streamButtonLabel(s: Stream, index: number): string {
  if (isAceStream(s)) return "Лучшее качество";
  if (s.source === "prime") return "PRIME";
  return `Источник #${index + 1}`;
}

function sourcePriority(s: Stream) {
  const u = s.url;
  if (isAceStream(s)) return -2;
  if (s.source === "prime") return -1;
  if (/vk\.com|vkvideo\.ru|vkvideo\.rs/.test(u)) return 0;
  if (/rutube\.ru/.test(u)) return 2;
  if (/ok\.ru/.test(u)) return 3;
  if (/embedded\.slevel\.ru/.test(u)) return 4;
  if (/\.m3u8/.test(u)) return 5;
  if (/youtube\.com|youtu\.be/.test(u)) return 6;
  if (/livetv/.test(u)) return 7;
  if (u.startsWith("acestream://")) return 8;
  return 9;
}

function sortStreams(list: Stream[]) {
  // acestream-источники показываем только в ТВ-приложении (там есть
  // свой плеер); в браузере они не воспроизводятся — скрываем
  const visible = list.filter((s) => !isAceStream(s));
  // webplayer livetv с youtube-транспортом — это тот же embed ролика;
  // через наш прокси YouTube показывает Error 153, поэтому приводим
  // URL к прямому embed и схлопываем дубли по URL.
  const seen = new Set<string>();
  return visible
    .map((s) => {
      let url = s.url;
      if (url.includes("webplayer") && url.includes("t=youtube")) {
        try {
          const u = new URL(url);
          const c = u.searchParams.get("c");
          const listId = u.searchParams.get("list");
          if (c || listId) {
            url = listId
              ? `https://www.youtube.com/embed/videoseries?list=${listId}`
              : `https://www.youtube.com/embed/${c}`;
          }
        } catch {}
      }
      return { ...s, url };
    })
    .sort((a, b) => sourcePriority(a) - sourcePriority(b))
    // дедуп после сортировки: при одинаковых URL выживает источник
    // с высшим приоритетом (PRIME, а не livetv-дубль того же embed)
    .filter((s) => {
      if (seen.has(s.url)) return false;
      seen.add(s.url);
      return true;
    });
}

export default function MatchPage() {
  const params = useParams<{ league: string; id: string }>();
  const [match, setMatch] = useState<Match | null>(null);
  const [selectedStream, setSelectedStream] = useState<Stream | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<MatchStatsData | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [rain, setRain] = useState<{ team: string; amount: number; donor: string; message: string; duration: number } | null>(null);
  const rainIdRef = useRef<number | null>(null);
  const [topDonations, setTopDonations] = useState<{ team: string; amount: number }[]>([]);
  const [gateSeen, setGateSeen] = useState(false);

  useEffect(() => {
    setGateSeen(gateAlreadySeen());
  }, []);

  // донат из гейта прошёл — гейт закрыт и запоминается
  useEffect(() => {
    const onDonated = () => {
      markGateSeen();
      setGateSeen(true);
    };
    window.addEventListener("hockey-donation-success", onDonated);
    return () => window.removeEventListener("hockey-donation-success", onDonated);
  }, []);

  const passGate = () => {
    markGateSeen();
    setGateSeen(true);
  };

  useEffect(() => {
    if (!params.id) return;
    fetch(`${API_URL}/api/schedule/${params.id}`)
      .then((r) => { if (!r.ok) throw new Error("Матч не найден"); return r.json(); })
      .then((data) => {
        if (data.league?.toLowerCase() !== params.league) {
          throw new Error("Несовпадение лиги");
        }
        setMatch(data);
        const ordered = sortStreams(data.stream_urls || []);
        if (ordered.length > 0) setSelectedStream(ordered[0]);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [params.league, params.id]);

  // Live/finished KHL/NHL статистика: для live — автообновление раз в 30 секунд
  useEffect(() => {
    if (!match || (match.league !== "KHL" && match.league !== "NHL")) return;
    if (match.status !== "live" && match.status !== "break" && match.status !== "finished") return;
    const date = (match.datetime_utc || "").slice(0, 10);
    const isLive = match.status === "live" || match.status === "break";
    const isNhl = match.league === "NHL";
    const url =
      `${API_URL}/api/match-stats?league=${match.league}&date=${date}` +
      `&home=${encodeURIComponent(match.team_home)}&away=${encodeURIComponent(match.team_away)}` +
      (match.match_uid ? `&uid=${encodeURIComponent(match.match_uid)}` : "") +
      (isLive ? "&live=1" : "");
    let stopped = false;
    setStatsLoading(true);
    let timer: ReturnType<typeof setInterval> | undefined;
    let hlAttempts = 0;
    const schedule = (ms: number) => {
      if (stopped) return;
      if (timer) clearInterval(timer);
      timer = setInterval(load, ms);
    };
    const load = () => {
      fetch(url)
        .then((r) => {
          if (!r.ok) throw new Error(`Статистика недоступна (${r.status})`);
          return r.json();
        })
        .then((s) => {
          if (!stopped) {
            setStats(s);
            setStatsError(null);
            if (isLive) {
              schedule(30000);
            } else if (isNhl) {
              // Обзор НХЛ (highlights) появляется на nhl.com через несколько
              // минут после финала: для свежих игр повторяем раз в минуту
              // (до 15 раз), старые грузим одним запросом
              const freshGame =
                Date.now() - parseMatchDate(match.datetime_utc).getTime() < 6 * 60 * 60 * 1000;
              if (s.highlights?.length || !freshGame || hlAttempts++ >= 15) {
                if (timer) clearInterval(timer);
                timer = undefined;
              } else {
                schedule(60000);
              }
            } else if (s.highlight?.m3u8_url) {
              if (timer) clearInterval(timer);
              timer = undefined;
            } else if (hlAttempts++ < 60) {
              // «Обзор матча» появляется с задержкой после финала —
              // проверяем раз в минуту (до часа), потом сдаёмся
              schedule(60000);
            }
          }
        })
        .catch((e) => {
          if (!stopped) setStatsError(e instanceof Error ? e.message : "Ошибка статистики");
        })
        .finally(() => {
          if (!stopped) setStatsLoading(false);
        });
    };
    load();
    return () => {
      stopped = true;
      if (timer) clearInterval(timer);
    };
  }, [match?.id, match?.status, match?.league, match?.datetime_utc, match?.team_home, match?.team_away, match?.match_uid]);

  const matchIdRef = useRef<number | undefined>(undefined);
  useEffect(() => { if (match) matchIdRef.current = match.id; }, [match]);

  useEffect(() => {
    if (!match) return;
    fetch(`${API_URL}/api/donations/top/${match.id}`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setTopDonations)
      .catch(() => {});
  }, [match?.id]);

  // оплата доната открылась popup-окном — после успеха обновляем топ
  useEffect(() => {
    if (!match?.id) return;
    const onMessage = (e: MessageEvent) => {
      if (e.data && e.data.type === "donation-success") {
        fetch(`${API_URL}/api/donations/top/${match.id}`)
          .then((r) => (r.ok ? r.json() : []))
          .then(setTopDonations)
          .catch(() => {});
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [match?.id]);

  const handleTestRain = async () => {
    if (!match) return;
    try {
      await fetch(`${API_URL}/api/donations/test-rain?match_id=${match.id}`, { method: "POST" });
    } catch {}
  };

  // SportPlusTV (ВХЛ): бэкенд не получает стримы с US IP,
  // поэтому тянем detail API напрямую из браузера пользователя.
  // МХЛ больше не берём — трансляции МХЛ идут через livetv.
  useEffect(() => {
    if (!match?.sp_match_id) return;
    if (match.league !== "VHL") return;
    const ctrl = new AbortController();
    fetchSportPlusTVStreams(match.sp_match_id, ctrl.signal)
      .then((extra) => {
        if (!extra.length) return;
        setMatch((prev) => {
          if (!prev) return prev;
          const known = new Set(prev.stream_urls.map((s) => s.url));
          const merged = [...prev.stream_urls, ...extra.filter((s) => !known.has(s.url))];
          return { ...prev, stream_urls: merged };
        });
      })
      .catch(() => {});
    return () => ctrl.abort();
  }, [match?.sp_match_id, match?.league]);

  // Трансляция 1win: live-матчи в линии 1win с видео. Ищем по названиям
  // команд; если трансляция появилась позже — повторяем поиск каждую минуту.
  useEffect(() => {
    if (!match || match.status !== "live") return;
    const ctrl = new AbortController();
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const attempt = (left: number) => {
      findWinBroadcast(match.team_home, match.team_away, match.datetime_utc, ctrl.signal)
        .then((found) => {
          if (stopped) return;
          if (found) {
            const s = winStream(found);
            setMatch((prev) => {
              if (!prev) return prev;
              if (prev.stream_urls.some((x) => x.url === s.url)) return prev;
              return { ...prev, stream_urls: [...prev.stream_urls, s] };
            });
            return;
          }
          if (left > 0) timer = setTimeout(() => attempt(left - 1), 60000);
        })
        .catch(() => {});
    };
    attempt(5);
    return () => {
      stopped = true;
      ctrl.abort();
      if (timer) clearTimeout(timer);
    };
  }, [match?.id, match?.status, match?.team_home, match?.team_away, match?.datetime_utc]);

  // Если источники появились позднее (клиентский fetch) — выбираем первый.
  useEffect(() => {
    if (selectedStream || !match?.stream_urls?.length) return;
    const ordered = sortStreams(match.stream_urls);
    if (ordered.length > 0) setSelectedStream(ordered[0]);
  }, [match?.stream_urls, selectedStream]);

  useEffect(() => {
    if (!match) return;
    const poll = async () => {
      try {
        const res = await fetch(`${API_URL}/api/donations/rain/${match.id}`);
        const data = await res.json();
        // одно событие показываем один раз (бэк отдаёт его всем поллерам
        // в течение RAIN_TTL — без id дождь перезапускался каждые 3 сек)
        if (data.rain && data.rain.id !== rainIdRef.current) {
          rainIdRef.current = data.rain.id as number;
          // бэк считает длительность от суммы доната (6..30 сек)
          const duration = (data.rain.duration as number) || 7;
          setRain({
            team: data.rain.team as string,
            amount: data.rain.amount as number,
            donor: data.rain.donor as string,
            message: (data.rain.message as string) || "",
            duration,
          });
          setTimeout(() => setRain(null), duration * 1000 + 800);
        }
      } catch {}
    };
    poll();
    const interval = setInterval(poll, 3000);
    return () => clearInterval(interval);
  }, [match?.id]);

  if (loading) return (
    <div className="pt-16 sm:pt-24 pb-4 sm:pb-16 max-w-[1400px] mx-auto px-3 sm:px-6 lg:px-8">
      <div className="animate-pulse space-y-4">
        <div className="h-5 bg-hockey-card rounded w-28" />
        <div className="w-full h-[60svh] sm:h-[75svh] lg:h-[calc(100svh-100px)] min-h-[280px] sm:min-h-[420px] bg-hockey-card rounded-xl" />
      </div>
    </div>
  );

  if (error || !match) return (
    <div className="pt-16 sm:pt-24 pb-4 sm:pb-16 max-w-[1400px] mx-auto px-3 sm:px-6 lg:px-8 text-center">
      <p className="text-hockey-accent mb-4 text-sm sm:text-base">{error || "Матч не найден"}</p>
      <Link href="/" className="text-hockey-text-secondary hover:text-white transition-colors text-sm">← Календарь</Link>
    </div>
  );

  const leagueLabel: Record<string, string> = { KHL: "КХЛ", VHL: "ВХЛ", MHL: "МХЛ", NHL: "НХЛ" };

  const sortedStreams = sortStreams(match.stream_urls);

  return (
    <div className="pt-16 sm:pt-24 pb-4 sm:pb-16">
      <div className="max-w-[1400px] mx-auto px-3 sm:px-6 lg:px-8">
        <Link href="/" className="inline-flex items-center gap-2 text-sm text-hockey-text-secondary hover:text-white transition-colors mb-4 sm:mb-6">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 19l-7-7 7-7"/></svg>
          Назад
        </Link>

        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <span className={`px-2 sm:px-2.5 py-0.5 sm:py-1 rounded text-[9px] sm:text-[10px] font-bold tracking-wider uppercase ${
            match.league === "KHL" ? "bg-hockey-khl/20 text-hockey-khl" :
            match.league === "MHL" ? "bg-hockey-mhl/20 text-hockey-mhl" :
            match.league === "NHL" ? "bg-hockey-accent/20 text-hockey-accent" :
            "bg-hockey-vhl/20 text-hockey-vhl"
          }`}>
            {leagueLabel[match.league] || match.league}
          </span>
          {match.status === "live" && (
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-hockey-live animate-pulse-live" />
              <span className="text-[10px] sm:text-[11px] font-bold text-hockey-live tracking-wider uppercase">LIVE</span>
            </div>
          )}
        </div>

        <h1 className="flex flex-wrap items-center gap-y-1 gap-x-2 sm:gap-x-3 text-lg sm:text-2xl lg:text-3xl font-black tracking-tight mb-1 leading-tight">
          <span className="inline-flex items-center gap-2 sm:gap-3">
            {getTeamLogo(match.team_home) && (
              <img src={getTeamLogo(match.team_home)!} alt="" className="w-8 h-8 sm:w-11 sm:h-11 object-contain" />
            )}
            <span className={match.team_home.length > 12 ? "text-base sm:text-xl lg:text-2xl" : ""}>{match.team_home}</span>
          </span>
          <span className="text-hockey-text-muted mx-1 sm:mx-2">vs</span>
          <span className="inline-flex items-center gap-2 sm:gap-3">
            <span className={match.team_away.length > 12 ? "text-base sm:text-xl lg:text-2xl" : ""}>{match.team_away}</span>
            {getTeamLogo(match.team_away) && (
              <img src={getTeamLogo(match.team_away)!} alt="" className="w-8 h-8 sm:w-11 sm:h-11 object-contain" />
            )}
          </span>
        </h1>
        {(match.status === "live" || match.status === "break" || match.status === "finished") && match.home_score != null && match.away_score != null && (
          <div className="flex items-center gap-3 mb-2">
            <span className="text-2xl sm:text-3xl font-black tabular-nums">
              {match.home_score} : {match.away_score}
            </span>
            {match.current_period && (match.status === "live" || match.status === "break") && (
              <span className="text-xs font-bold text-hockey-live uppercase">{match.current_period}</span>
            )}
          </div>
        )}
        <p className="text-xs sm:text-sm text-hockey-text-secondary mb-4 sm:mb-6">
          {parseMatchDate(match.datetime_utc).toLocaleString("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}
        </p>

        {match.status === "finished" && (match.league === "KHL" || match.league === "NHL") && (
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
            {stats && <MatchStats data={stats} tabs />}
          </div>
        )}
        {/* завершённые КХЛ/НХЛ — без плеера трансляции: обзор идёт внутри статистики */}
        {!(match.status === "finished" && (match.league === "KHL" || match.league === "NHL")) && (
          <>
            {sortedStreams.length > 0 && (
              <div className="flex flex-nowrap gap-2 mb-3 sm:mb-4 overflow-x-auto pb-1 scrollbar-hide">
                {sortedStreams.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => setSelectedStream(s)}
                    className={`shrink-0 px-3 sm:px-4 py-1.5 sm:py-2 rounded-lg text-xs sm:text-sm font-semibold transition-all duration-200 ${
                      selectedStream?.url === s.url
                        ? "bg-hockey-accent text-white shadow-lg shadow-hockey-accent/20"
                        : "bg-hockey-card border border-hockey-border text-hockey-text-secondary hover:text-white hover:border-hockey-border-light"
                    }`}
                  >
                    {streamButtonLabel(s, i)}
                  </button>
                ))}
              </div>
            )}

            {sortedStreams.length === 0 && match.status !== "finished" && (
              <div className="glass rounded-2xl p-4 sm:p-6 text-center">
                <p className="text-hockey-text-secondary text-sm">
                  Трансляция этого матча отсутствует
                </p>
              </div>
            )}

            {sortedStreams.length > 0 && (
              <p className="text-[11px] sm:text-xs text-hockey-text-muted mb-3 sm:mb-4">
                Любая реклама в трансляциях не имеет никакого отношения к нашему сервису.
              </p>
            )}

            {selectedStream && (
              <div className="relative z-10">
                {gateSeen ? (
                  <StreamPlayer key={selectedStream.url} url={selectedStream.url} title={`${match.team_home} vs ${match.team_away}`} />
                ) : (
                  <PlayerGate
                    matchId={match.id}
                    teamHome={match.team_home}
                    teamAway={match.team_away}
                    onWatch={passGate}
                  />
                )}
              </div>
            )}
          </>
        )}

        <DonateButtons
          matchId={match.id}
          teamHome={match.team_home}
          teamAway={match.team_away}
          league={match.league}
        />

        {topDonations.length > 0 && (
          <div className="mt-4">
            <p className="text-[10px] sm:text-xs text-hockey-text-muted mb-2 uppercase tracking-wider font-bold">
              Лучшие болельщики
            </p>
            <div className="space-y-1.5">
              {topDonations.slice(0, 5).map((d, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between px-3 py-2 rounded-lg bg-hockey-card border border-hockey-border"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-[10px] font-bold text-hockey-text-muted w-4">{i + 1}</span>
                    <span className="text-xs sm:text-sm font-bold truncate">{d.team}</span>
                  </div>
                  <span className="text-xs sm:text-sm font-black text-hockey-accent tabular-nums">
                    {d.amount} ₽
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {(match.league === "KHL" || match.league === "NHL") && (match.status === "live" || match.status === "break") && (
          <div className="mt-6">
            {statsLoading && !stats && (
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
            {stats && <MatchStats data={stats} tabs />}
          </div>
        )}

        <button
          onClick={handleTestRain}
          className="mt-4 px-4 py-2 rounded-lg bg-hockey-card border border-hockey-border text-xs text-hockey-text-muted hover:text-white hover:border-hockey-border-light transition-all"
        >
           Тест дождя
        </button>

        {rain && (
          <DonationRain team={rain.team} amount={rain.amount} donor={rain.donor} message={rain.message} duration={rain.duration} />
        )}
      </div>
    </div>
  );
}
