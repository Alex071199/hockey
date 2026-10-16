"use client";

import { useEffect, useState } from "react";

import { getTeamLogo } from "@/lib/team-logos";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

const TEAM_RU: Record<string, string> = {
  "Lokomotiv Yaroslavl": "Локомотив",
  "Nizhny Novgorod": "Торпедо",
  "SKA St. Petersburg": "СКА",
  "Spartak Moscow": "Спартак",
  "Kunlun": "Драконы",
  "Cherepovets": "Северсталь",
  "CSKA Moscow": "ЦСКА",
  "Dynamo Moscow": "Динамо М",
  "Dinamo Minsk": "Динамо Минск",
  "Lada": "Лада",
  "Sochi": "ХК Сочи",
  "Bars Kazan": "Ак Барс",
  "Magnitogorsk": "Металлург Мг",
  "Nizhnekamsk": "Нефтехимик",
  "Barys Astana": "Барыс",
  "Salavat Ufa": "Салават Юлаев",
  "Vladivostok": "Адмирал",
  "Yekaterinburg": "Автомобилист",
  "Novosibirsk": "Сибирь",
  "Avangard Omsk": "Авангард",
  "Tractor Chelyabinsk": "Трактор",
  "Khabarovsk": "Амур",
};

const GROUP_RU: Record<string, string> = {
  "Western Conference": "Западная конференция",
  "Eastern Conference": "Восточная конференция",
  "Bobrov Division": "Дивизион Боброва",
  "Tarasov Division": "Дивизион Тарасова",
  "Kharlamov Division": "Дивизион Харламова",
  "Chernyshev Division": "Дивизион Чернышева",
};

interface StandingRow {
  position: number;
  team_id: number | null;
  team_name: string;
  logo: string;
  played: number;
  wins: number;
  ot_wins: number;
  ot_losses: number;
  losses: number;
  goals_for: number;
  goals_against: number;
  points: number;
}

interface Group {
  name: string;
  rows: StandingRow[];
}

interface StandingsResponse {
  league: string;
  season: number;
  updated_at: string;
  stale: boolean;
  groups: Group[];
}

const ru = (name: string, map: Record<string, string>) => map[name] ?? name;

function TeamCell({ name, fallbackLogo }: { name: string; fallbackLogo: string }) {
  // Свои логотипы в приоритете, логотип из API — только как запасной
  const [src, setSrc] = useState<string | null>(getTeamLogo(name) ?? fallbackLogo ?? null);
  useEffect(() => {
    setSrc(getTeamLogo(name) ?? fallbackLogo ?? null);
  }, [name, fallbackLogo]);
  return (
    <span className="flex items-center gap-2 font-semibold">
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt=""
          className="w-6 h-6 object-contain shrink-0"
          loading="lazy"
          onError={() => {
            if (src !== fallbackLogo) setSrc(fallbackLogo || null);
          }}
        />
      ) : null}
      {name}
    </span>
  );
}

function GroupTable({ group, playoffLine }: { group: Group; playoffLine: boolean }) {
  return (
    <section className="glass rounded-2xl p-3 sm:p-6 overflow-x-auto">
      <h2 className="text-lg sm:text-xl font-extrabold uppercase tracking-tight mb-4">
        {ru(group.name, GROUP_RU)}
      </h2>
      <table className="w-full text-sm min-w-[640px]">
        <thead>
          <tr className="text-left text-xs uppercase opacity-60 border-b border-white/10">
            <th className="py-2 pr-2 w-8 text-center">#</th>
            <th className="py-2 pr-2">Команда</th>
            <th className="py-2 px-1 text-center" title="Игры">И</th>
            <th className="py-2 px-1 text-center" title="Победы">В</th>
            <th className="py-2 px-1 text-center" title="Победы в овертайме/буллитах">ВО</th>
            <th className="py-2 px-1 text-center" title="Поражения в овертайме/буллитах">ПО</th>
            <th className="py-2 px-1 text-center" title="Поражения">П</th>
            <th className="py-2 px-1 text-center" title="Шайбы">Ш</th>
            <th className="py-2 pl-1 text-center font-bold" title="Очки">О</th>
          </tr>
        </thead>
        <tbody>
          {group.rows.map((r) => (
            <tr
              key={`${r.team_id}-${r.team_name}`}
              className={`border-b border-white/5 last:border-0 hover:bg-white/5 ${
                playoffLine && r.position === 8 ? "border-b-2 border-b-[#791529]" : ""
              }`}
            >
              <td className="py-2 pr-2 text-center opacity-70">{r.position}</td>
              <td className="py-2 pr-2">
                <TeamCell name={ru(r.team_name, TEAM_RU)} fallbackLogo={r.logo} />
              </td>
              <td className="py-2 px-1 text-center opacity-80">{r.played}</td>
              <td className="py-2 px-1 text-center">{r.wins}</td>
              <td className="py-2 px-1 text-center">{r.ot_wins}</td>
              <td className="py-2 px-1 text-center">{r.ot_losses}</td>
              <td className="py-2 px-1 text-center">{r.losses}</td>
              <td className="py-2 px-1 text-center opacity-80 whitespace-nowrap">
                {r.goals_for}–{r.goals_against}
              </td>
              <td className="py-2 pl-1 text-center font-extrabold">{r.points}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default function StandingsPage() {
  const [data, setData] = useState<StandingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      fetch(`${API_URL}/api/standings?league=KHL`)
        .then((res) => {
          if (!res.ok) throw new Error(`API: ${res.status}`);
          return res.json();
        })
        .then((json: StandingsResponse) => {
          if (!cancelled) {
            setData(json);
            setError(null);
          }
        })
        .catch((e) => {
          if (!cancelled && !data) setError(e instanceof Error ? e.message : "Ошибка загрузки");
        });
    };
    load();
    const timer = setInterval(load, 5 * 60 * 1000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const conferences = (data?.groups ?? []).filter((g) => g.name.includes("Conference"));
  const divisions = (data?.groups ?? []).filter((g) => !g.name.includes("Conference"));

  return (
    <main className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 pt-20 sm:pt-24 pb-8 sm:pb-16">
      <div className="flex items-baseline gap-3 flex-wrap mb-6 sm:mb-8">
        <h1 className="text-2xl sm:text-3xl font-black tracking-tight uppercase">
          Турнирная таблица
        </h1>
        {data && (
          <span className="text-xs opacity-60">
            КХЛ · сезон {data.season}/{String((data.season + 1) % 100).padStart(2, "0")}
          </span>
        )}
      </div>

      {error && (
        <div className="glass rounded-2xl p-6 text-center text-red-400">
          Не удалось загрузить таблицу: {error}
        </div>
      )}

      {!data && !error && (
        <div className="glass rounded-2xl p-3 sm:p-6 space-y-3 animate-pulse" aria-hidden>
          {[95, 88, 92, 85, 90, 87, 91, 86].map((w, i) => (
            <div key={i} className="h-10 rounded-lg bg-hockey-card" style={{ width: `${w}%` }} />
          ))}
        </div>
      )}

      {data && (
        <div className="space-y-6">
          {conferences.map((g) => (
            <GroupTable key={g.name} group={g} playoffLine />
          ))}
          {divisions.length > 0 && (
            <details className="glass rounded-2xl p-3 sm:p-6">
              <summary className="cursor-pointer font-extrabold uppercase tracking-tight">
                Дивизионы
              </summary>
              <div className="space-y-6 mt-4">
                {divisions.map((g) => (
                  <GroupTable key={g.name} group={g} playoffLine={false} />
                ))}
              </div>
            </details>
          )}
        </div>
      )}
    </main>
  );
}
