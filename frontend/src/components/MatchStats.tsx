"use client";

interface FormEntry {
  id: number;
  date: string;
  home: string;
  away: string;
  score_home: number | null;
  score_away: number | null;
  finish: "reg" | "ot" | "so";
}

interface SeasonEntry {
  leagueName: string;
  season: number;
  total: { games: { played: number; wins: number; loses: number }; goals: { scored: number; received: number } };
  home: { games: { played: number; wins: number; loses: number }; goals: { scored: number; received: number } };
  away: { games: { played: number; wins: number; loses: number }; goals: { scored: number; received: number } };
}

interface Prediction {
  modelType: string;
  description: string;
  probabilities: Record<string, string>;
}

export interface MatchStatsData {
  league: string;
  partial?: string[];
  match: {
    home: string;
    away: string;
    status: string;
    score_home: number;
    score_away: number;
    finish: "reg" | "ot" | "so";
  };
  periods: Record<string, string | null>;
  venue: { city?: string; name?: string; capacity?: string } | null;
  predictions: Prediction[];
  form: { home: FormEntry[]; away: FormEntry[] };
  h2h: FormEntry[];
  season_stats: { home: SeasonEntry[]; away: SeasonEntry[] };
}

function parsePair(s: string | null): [number, number] | null {
  if (!s) return null;
  const parts = s.split("-");
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

function resultOf(e: FormEntry, team: string): "W" | "L" | "?" {
  if (e.score_home === null || e.score_away === null) return "?";
  const mine = team === e.home ? e.score_home : e.score_away;
  const theirs = team === e.home ? e.score_away : e.score_home;
  return mine > theirs ? "W" : "L";
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
  const max = Math.max(1, ...rows.flatMap((r) => r.pair));
  return (
    <div className="space-y-2.5">
      {rows.map((r) => (
        <div key={r.label}>
          <div className="flex justify-between text-xs mb-1">
            <span className="font-bold tabular-nums">{r.pair[0]}</span>
            <span className="opacity-60">{r.label}</span>
            <span className="font-bold tabular-nums">{r.pair[1]}</span>
          </div>
          <div className="flex gap-1 h-2">
            <div className="flex-1 flex justify-end bg-white/5 rounded-full overflow-hidden">
              <div className="bg-hockey-accent rounded-full" style={{ width: `${(r.pair[0] / max) * 100}%` }} />
            </div>
            <div className="flex-1 bg-white/5 rounded-full overflow-hidden">
              <div className="bg-sky-400/80 rounded-full" style={{ width: `${(r.pair[1] / max) * 100}%` }} />
            </div>
          </div>
        </div>
      ))}
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

function FormBadges({ entries, team }: { entries: FormEntry[]; team: string }) {
  if (!entries.length) return <p className="text-xs opacity-60">Нет данных</p>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map((e) => {
        const r = resultOf(e, team);
        const extra = e.finish === "ot" ? "ОТ" : e.finish === "so" ? "Б" : "";
        return (
          <span
            key={e.id}
            title={`${e.home} ${e.score_home}:${e.score_away} ${e.away} · ${shortDate(e.date)}`}
            className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-bold tabular-nums ${
              r === "W" ? "bg-emerald-500/15 text-emerald-300" : "bg-[#791529]/25 text-red-300"
            }`}
          >
            {r === "W" ? "В" : "П"} {e.score_home}:{e.score_away}
            {extra && <span className="opacity-70 font-semibold">{extra}</span>}
          </span>
        );
      })}
    </div>
  );
}

function SeasonBlock({ entries, label }: { entries: SeasonEntry[]; label: string }) {
  const s = entries.find((e) => e.leagueName === "KHL") ?? entries[0];
  if (!s) return <p className="text-xs opacity-60">Нет данных</p>;
  const t = s.total;
  return (
    <div className="text-sm">
      <p className="text-xs opacity-60 mb-2">
        {label} · сезон {s.season}/{String((s.season + 1) % 100).padStart(2, "0")}
      </p>
      <div className="grid grid-cols-4 gap-2 text-center">
        {[
          ["И", t.games.played],
          ["В", t.games.wins],
          ["П", t.games.loses],
          ["Ш", `${t.goals.scored}–${t.goals.received}`],
        ].map(([k, v]) => (
          <div key={k} className="bg-white/5 rounded-xl py-2">
            <div className="text-[10px] opacity-60 uppercase">{k}</div>
            <div className="font-extrabold tabular-nums">{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function MatchStats({ data }: { data: MatchStatsData }) {
  const m = data.match;
  const pred = data.predictions.find((p) => p.modelType === "three-way") ?? data.predictions[0];
  const probs = pred ? Object.entries(pred.probabilities) : [];
  const maxProb = Math.max(1, ...probs.map(([, v]) => parseFloat(v) || 0));

  return (
    <div className="space-y-4 sm:space-y-6">
      {data.partial && data.partial.length > 0 && (
        <p className="text-xs opacity-60 text-center">
          Часть разделов временно недоступна (лимит API), остальное ниже
        </p>
      )}
      <section className="glass rounded-2xl p-4 sm:p-6">
        <div className="flex items-center justify-center gap-3 sm:gap-5 mb-5">
          <p className="flex-1 text-base sm:text-xl font-extrabold text-right">{m.home}</p>
          <div className="text-center leading-none">
            <div className="text-3xl sm:text-4xl font-black tabular-nums whitespace-nowrap">
              {m.score_home} : {m.score_away}
            </div>
            {m.finish === "ot" && <div className="text-xs font-bold opacity-60 mt-1">ОТ</div>}
            {m.finish === "so" && <div className="text-xs font-bold opacity-60 mt-1">Б</div>}
          </div>
          <p className="flex-1 text-base sm:text-xl font-extrabold text-left">{m.away}</p>
        </div>
        <PeriodChart periods={data.periods} home={m.home} away={m.away} />
        {data.venue?.name && (
          <p className="text-xs opacity-60 mt-4 text-center">
            {data.venue.name}
            {data.venue.city ? ` · ${data.venue.city}` : ""}
            {data.venue.capacity ? ` · ${data.venue.capacity} мест` : ""}
          </p>
        )}
      </section>

      {pred && (
        <section className="glass rounded-2xl p-4 sm:p-6">
          <h3 className="text-sm font-extrabold uppercase tracking-wide mb-1">Прогноз</h3>
          <p className="text-xs opacity-70 mb-3">{pred.description}</p>
          <div className="space-y-2">
            {probs.map(([k, v]) => (
              <div key={k}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="uppercase opacity-70">{k === "home" ? m.home : k === "away" ? m.away : "Ничья"}</span>
                  <span className="font-bold tabular-nums">{v}</span>
                </div>
                <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                  <div className="h-full bg-hockey-accent rounded-full" style={{ width: `${(parseFloat(v) / maxProb) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="glass rounded-2xl p-4 sm:p-6">
        <h3 className="text-sm font-extrabold uppercase tracking-wide mb-3">Форма · последние 5</h3>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <p className="text-xs font-bold mb-2">{m.home}</p>
            <FormBadges entries={data.form.home} team={m.home} />
          </div>
          <div>
            <p className="text-xs font-bold mb-2">{m.away}</p>
            <FormBadges entries={data.form.away} team={m.away} />
          </div>
        </div>
      </section>

      <section className="glass rounded-2xl p-4 sm:p-6">
        <h3 className="text-sm font-extrabold uppercase tracking-wide mb-3">Очные встречи</h3>
        {data.h2h.length === 0 && <p className="text-xs opacity-60">Нет данных</p>}
        <div className="space-y-1.5">
          {data.h2h.slice(0, 10).map((e) => (
            <div key={e.id} className="flex items-center justify-between text-xs sm:text-sm gap-2">
              <span className="opacity-60 tabular-nums flex-shrink-0">{shortDate(e.date)}</span>
              <span className="truncate">
                {e.home} – {e.away}
              </span>
              <span className="font-extrabold tabular-nums flex-shrink-0">
                {e.score_home}:{e.score_away}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="glass rounded-2xl p-4 sm:p-6">
        <h3 className="text-sm font-extrabold uppercase tracking-wide mb-3">Сезон</h3>
        <div className="grid sm:grid-cols-2 gap-4">
          <SeasonBlock entries={data.season_stats.home} label={m.home} />
          <SeasonBlock entries={data.season_stats.away} label={m.away} />
        </div>
      </section>
    </div>
  );
}
