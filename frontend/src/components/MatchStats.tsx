"use client";

import { useLayoutEffect, useRef, useState } from "react";
import HlsVideo from "@/components/HlsVideo";

export interface MatchStatsData {
  league: string;
  event_id: number;
  match: {
    home: string;
    away: string;
    home_team_id: number;
    away_team_id: number;
    status: string;
    score_home: number;
    score_away: number;
    finish: "reg" | "ot" | "so";
  };
  periods: Record<string, string | null>;
  team_stats: {
    home: TeamStats;
    away: TeamStats;
  };
  goals: GoalEntry[];
  penalties: PenaltyEntry[];
  rosters?: {
    home: RosterPlayer[];
    away: RosterPlayer[];
  };
  highlight?: {
    m3u8_url: string;
    name?: string;
  } | null;
  /** НХЛ: обзор матча (ролики Brightcove с nhl.com) — рендерится в этой же
   *  статистике после шапки со счётом, перед вкладками «Статистика/Составы». */
  highlights?: {
    video_id: string;
    slug?: string;
    embed_url: string;
  }[];
}

interface RosterPlayer {
  number: number | null;
  name: string;
  role: string;
  image?: string | null;
  goals?: number;
}

interface TeamStats {
  shots: number;
  goals_for: number;
  ppg: number;
  shg: number;
  ppc: number;
  faceoffs_won: number;
  pim: number;
  puck_control_pct: number;
  distance_km: number;
  zone_entries: number;
}

interface GoalEntry {
  time: string;
  score: string;
  period: number;
  team_id: number;
  scorer: string;
  assistants: string[];
}

interface PenaltyEntry {
  time: string;
  period: number;
  reason: string;
  minutes: number;
  player: string;
  team_id: number;
}

function parsePair(s: string | null): [number, number] | null {
  if (!s) return null;
  const parts = s.split(":");
  if (parts.length !== 2) return null;
  const a = parseInt(parts[0].trim(), 10);
  const b = parseInt(parts[1].trim(), 10);
  if (Number.isNaN(a) || Number.isNaN(b)) return null;
  return [a, b];
}

function shortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

function StatBar({ home, away, label }: { home: number; away: number; label: string }) {
  const total = home + away;
  const isZero = total === 0;
  const homePct = total > 0 ? (home / total) * 100 : 50;
  const barStyle: React.CSSProperties = isZero
    ? { height: "8px", borderRadius: "9999px", border: "1px solid rgba(255,255,255,0.15)" }
    : { position: "relative", height: "8px", borderRadius: "9999px", background: "rgba(255,255,255,0.05)", overflow: "hidden" };
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="font-bold tabular-nums">{home}</span>
        <span className="text-hockey-text-muted">{label}</span>
        <span className="font-bold tabular-nums">{away}</span>
      </div>
      <div style={barStyle}>
        {!isZero && (
          <>
            <div style={{ position: "absolute", top: 0, bottom: 0, left: 0, width: `${homePct}%`, borderRadius: "9999px 0 0 9999px", background: "#e11d48" }} />
            <div style={{ position: "absolute", top: 0, bottom: 0, right: 0, width: `${100 - homePct}%`, borderRadius: "0 9999px 9999px 0", background: "#ffffff" }} />
          </>
        )}
      </div>
    </div>
  );
}

function PeriodChart({ periods, home, away }: { periods: Record<string, string | null>; home: string; away: string }) {
  const rows: { label: string; pair: [number, number] }[] = [];
  const defs: [string, string][] = [
    ["first", "1-й период"],
    ["second", "2-й период"],
    ["third", "3-й период"],
    ["overtime", "Овертайм"],
  ];
  for (const [key, label] of defs) {
    const p = parsePair(periods[key]);
    if (p) rows.push({ label, pair: p });
  }
  const pen = parsePair(periods["penalties"]);
  if (!rows.length && !pen) return null;
  return (
    <div className="space-y-2.5">
      {rows.map((r) => {
        const total = r.pair[0] + r.pair[1];
        const isZero = total === 0;
        const homePct = total > 0 ? (r.pair[0] / total) * 100 : 0;
        const barStyle: React.CSSProperties = isZero
          ? { height: "8px", borderRadius: "9999px", border: "1px solid rgba(255,255,255,0.15)" }
          : { position: "relative", height: "8px", borderRadius: "9999px", background: "rgba(255,255,255,0.05)", overflow: "hidden" };
        return (
          <div key={r.label}>
            <div className="flex justify-between text-xs mb-1">
              <span className="font-bold tabular-nums">{r.pair[0]}</span>
              <span className="opacity-60">{r.label}</span>
              <span className="font-bold tabular-nums">{r.pair[1]}</span>
            </div>
            <div style={barStyle}>
              {!isZero && (
                <>
                  <div style={{ position: "absolute", top: 0, bottom: 0, left: 0, width: `${homePct}%`, borderRadius: "9999px 0 0 9999px", background: "#e11d48" }} />
                  <div style={{ position: "absolute", top: 0, bottom: 0, right: 0, width: `${100 - homePct}%`, borderRadius: "0 9999px 9999px 0", background: "#ffffff" }} />
                </>
              )}
            </div>
          </div>
        );
      })}
      {pen && (
        <div className="flex justify-between text-xs pt-1">
          <span className="font-bold tabular-nums">{pen[0]}</span>
          <span className="opacity-60">Буллиты</span>
          <span className="font-bold tabular-nums">{pen[1]}</span>
        </div>
      )}
      <div className="flex justify-between text-[11px] opacity-60 pt-1">
        <span>{home}</span>
        <span>{away}</span>
      </div>
    </div>
  );
}

function GoalScorers({ goals, homeTeamId, awayTeamId, homeName, awayName }: { goals: GoalEntry[]; homeTeamId: number; awayTeamId: number; homeName: string; awayName: string }) {
  if (!goals.length) return null;
    return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-3 text-[10px] text-hockey-text-muted mb-1">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full inline-block" style={{ background: "#e11d48" }} /> {homeName}</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full inline-block" style={{ background: "#ffffff" }} /> {awayName}</span>
      </div>
      {goals.map((g, i) => {
        const isHome = g.team_id === homeTeamId;
        return (
          <div key={i} className="flex items-center gap-2 text-xs">
            <span className="text-hockey-text-muted tabular-nums w-12 text-right flex-shrink-0">{g.time}</span>
            <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: isHome ? "#e11d48" : "#ffffff" }} />
            <span className="font-bold">{g.scorer}</span>
            {g.assistants.length > 0 && (
              <span className="text-hockey-text-muted">({g.assistants.join(", ")})</span>
            )}
            <span className="ml-auto font-bold tabular-nums">{g.score}</span>
          </div>
        );
      })}
    </div>
  );
}

function PenaltiesList({ penalties, homeTeamId, homeName, awayName }: { penalties: PenaltyEntry[]; homeTeamId: number; homeName: string; awayName: string }) {
  if (!penalties.length) return null;
  return (
    <div className="space-y-1.5">
      {penalties.map((p, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          <span className="text-hockey-text-muted tabular-nums w-12 text-right flex-shrink-0">{p.time}</span>
          <span className="text-yellow-400 font-bold tabular-nums w-6 text-center flex-shrink-0">{p.minutes}&#x2019;</span>
          <span className="font-bold truncate">{p.player}</span>
          <span className="text-hockey-text-muted truncate">({p.team_id === homeTeamId ? homeName : awayName})</span>
          <span className="text-hockey-text-muted truncate hidden sm:inline">{p.reason}</span>
        </div>
      ))}
    </div>
  );
}

const ROLE_ORDER: Record<string, number> = { goaltender: 0, defensemen: 1, forward: 2 };
const ROLE_LABELS: Record<string, string> = {
  goaltender: "Вратари",
  defensemen: "Защитники",
  forward: "Нападающие",
};

function RosterList({ players, accent }: { players: RosterPlayer[]; accent: string }) {
  const byRole = new Map<string, RosterPlayer[]>();
  for (const p of players) {
    const key = p.role || "other";
    if (!byRole.has(key)) byRole.set(key, []);
    byRole.get(key)!.push(p);
  }
  const roles = Array.from(byRole.keys()).sort(
    (a, b) => (ROLE_ORDER[a] ?? 9) - (ROLE_ORDER[b] ?? 9)
  );

  return (
    <div className="space-y-4">
      {roles.map((role) => {
        const items = byRole
          .get(role)!
          .slice()
          .sort((a, b) => (a.number ?? 999) - (b.number ?? 999));
        return (
          <div key={role}>
            <div className="flex items-center gap-2 mb-2">
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: accent }} />
              <span className="text-[10px] font-bold uppercase tracking-widest text-hockey-text-muted">
                {ROLE_LABELS[role] ?? "Состав"}
              </span>
            </div>
            <div className="space-y-1">
              {items.map((p, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="w-6 text-right font-black tabular-nums text-hockey-text-muted shrink-0">
                    {p.number ?? "—"}
                  </span>
                  {p.image ? (
                    <img
                      src={p.image}
                      alt=""
                      loading="lazy"
                      className="w-6 h-6 rounded-full object-cover bg-white/10 shrink-0"
                    />
                  ) : (
                    <span className="w-6 h-6 rounded-full bg-white/10 shrink-0" />
                  )}
                  <span className="font-bold truncate">{p.name}</span>
                  {(p.goals ?? 0) > 0 && (
                    <span className="ml-auto text-[10px] font-black px-1.5 py-0.5 rounded bg-hockey-accent/20 text-hockey-accent tabular-nums shrink-0">
                      {p.goals} Г
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function MatchStats({ data, tabs = false }: { data: MatchStatsData; tabs?: boolean }) {
  const [tab, setTab] = useState<"stats" | "rosters">("stats");
  const m = data.match;
  const hs = data.team_stats.home;
  const as_ = data.team_stats.away;

  const faceoffsHome = hs.faceoffs_won;
  const faceoffsAway = as_.faceoffs_won;
  const totalFaceoffs = faceoffsHome + faceoffsAway;
  const faceoffHomePct = totalFaceoffs > 0 ? Math.round((faceoffsHome / totalFaceoffs) * 100) : 50;
  const faceoffAwayPct = 100 - faceoffHomePct;

  const hasRosters = !!(
    data.rosters && (data.rosters.home.length > 0 || data.rosters.away.length > 0)
  );
  // вкладки всегда при tabs=true: «Статистика» / «Составы» вместо секций подряд
  const showTabs = tabs;
  const goals = data.goals ?? [];
  const penalties = data.penalties ?? [];

  const hlCount = data.highlights?.length ?? 0;
  const hlWrapRef = useRef<HTMLDivElement>(null);
  const [hlHeight, setHlHeight] = useState<number | null>(null);

  useLayoutEffect(() => {
    const el = hlWrapRef.current;
    if (!el || hlCount === 0) return;
    const calc = () => {
      const pageTop = el.getBoundingClientRect().top + window.scrollY;
      const avail = window.innerHeight - pageTop - 24;
      setHlHeight(avail >= 200 ? Math.round(avail) : null);
    };
    calc();
    window.addEventListener("resize", calc);
    return () => window.removeEventListener("resize", calc);
  }, [hlCount]);

  const statsSections = (
    <>
      <section className="glass rounded-2xl p-4 sm:p-6">
        <h3 className="text-sm font-extrabold uppercase tracking-wide mb-4">Статистика матча</h3>
        <div className="space-y-3">
          <StatBar home={hs.shots} away={as_.shots} label="Броски" />
          <StatBar home={faceoffsHome} away={faceoffsAway} label={`Вбрасывания (${faceoffHomePct}% / ${faceoffAwayPct}%)`} />
          <StatBar home={hs.ppg} away={as_.ppg} label="Голы в большинстве" />
          <StatBar home={hs.shg} away={as_.shg} label="Голы в меньшинстве" />
          <StatBar home={hs.pim} away={as_.pim} label="Минуты штрафа" />
        </div>
      </section>

      {goals.length > 0 && (
        <section className="glass rounded-2xl p-4 sm:p-6">
          <h3 className="text-sm font-extrabold uppercase tracking-wide mb-3">Голы</h3>
          <GoalScorers goals={goals} homeTeamId={m.home_team_id} awayTeamId={m.away_team_id} homeName={m.home} awayName={m.away} />
        </section>
      )}

      {penalties.length > 0 && (
        <section className="glass rounded-2xl p-4 sm:p-6">
          <h3 className="text-sm font-extrabold uppercase tracking-wide mb-3">Штрафы</h3>
          <PenaltiesList penalties={penalties} homeTeamId={m.home_team_id} homeName={m.home} awayName={m.away} />
        </section>
      )}
    </>
  );

  const rostersSection = (
    <section className="glass rounded-2xl p-4 sm:p-6">
      {hasRosters ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 sm:gap-8">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <span className="w-2 h-2 rounded-full" style={{ background: "#e11d48" }} />
              <p className="text-xs font-extrabold uppercase tracking-wide truncate">{m.home}</p>
            </div>
            {data.rosters && data.rosters.home.length > 0 ? (
              <RosterList players={data.rosters.home} accent="#e11d48" />
            ) : (
              <p className="text-sm text-hockey-text-muted py-4">Состав недоступен</p>
            )}
          </div>
          <div>
            <div className="flex items-center gap-2 mb-3">
              <span className="w-2 h-2 rounded-full" style={{ background: "#ffffff" }} />
              <p className="text-xs font-extrabold uppercase tracking-wide truncate">{m.away}</p>
            </div>
            {data.rosters && data.rosters.away.length > 0 ? (
              <RosterList players={data.rosters.away} accent="#ffffff" />
            ) : (
              <p className="text-sm text-hockey-text-muted py-4">Состав недоступен</p>
            )}
          </div>
        </div>
      ) : (
        <p className="text-center text-sm text-hockey-text-secondary py-6">
          Составы недоступны для этого матча
        </p>
      )}
    </section>
  );

  return (
    <div className="space-y-4 sm:space-y-6">
      <section className="glass rounded-2xl p-4 sm:p-6">
        <div className="flex items-center justify-center gap-3 sm:gap-5 mb-5">
          <p className={`flex-1 font-extrabold text-right ${m.home.length > 12 ? 'text-sm sm:text-lg' : 'text-base sm:text-xl'}`}>{m.home}</p>
          <div className="text-center leading-none">
            <div className="text-3xl sm:text-4xl font-black tabular-nums whitespace-nowrap">
              {m.score_home} : {m.score_away}
            </div>
            {m.finish === "ot" && <div className="text-xs font-bold opacity-60 mt-1">ОТ</div>}
            {m.finish === "so" && <div className="text-xs font-bold opacity-60 mt-1">Б</div>}
          </div>
          <p className={`flex-1 font-extrabold text-left ${m.away.length > 12 ? 'text-sm sm:text-lg' : 'text-base sm:text-xl'}`}>{m.away}</p>
        </div>
        <PeriodChart periods={data.periods} home={m.home} away={m.away} />
      </section>

      {(data.highlights?.length ?? 0) > 0 && (
        <section>
          <h3 className="text-sm font-extrabold uppercase tracking-wide mb-3">Обзор матча</h3>
          <div
            ref={hlWrapRef}
            className="relative left-1/2 -translate-x-1/2 w-screen aspect-video bg-black border-y border-hockey-border"
            style={hlHeight ? { height: `${hlHeight}px` } : undefined}
          >
            {data.highlights!.map((h) => (
              <iframe
                key={h.video_id}
                src={h.embed_url}
                title="Обзор матча НХЛ"
                allow="autoplay; fullscreen; picture-in-picture"
                allowFullScreen
                loading="lazy"
                className="absolute inset-0 w-full h-full border-0"
              />
            ))}
          </div>
        </section>
      )}

      {data.highlight?.m3u8_url && (
        <section>
          <h3 className="text-sm font-extrabold uppercase tracking-wide mb-3">Обзор матча</h3>
          <HlsVideo
            compact
            retry={3}
            url={data.highlight.m3u8_url}
            title={data.highlight.name || "Обзор матча"}
          />
        </section>
      )}

      {showTabs && (
        <div className="inline-flex gap-1 rounded-xl bg-hockey-card border border-hockey-border p-1">
          {([["stats", "Статистика"], ["rosters", "Составы"]] as const).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`px-4 sm:px-5 py-1.5 rounded-lg text-xs sm:text-sm font-bold transition-all duration-200 ${
                tab === key
                  ? "bg-hockey-accent text-white shadow-lg shadow-hockey-accent/20"
                  : "text-hockey-text-secondary hover:text-white"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {showTabs ? (
        tab === "stats" ? statsSections : rostersSection
      ) : (
        <>
          {statsSections}
          {rostersSection}
        </>
      )}
    </div>
  );
}
