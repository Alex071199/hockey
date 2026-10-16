// Общие хелперы для счёта завершённых матчей (Highlightly -> наши названия).

export interface ScoreResult {
  home: string;
  away: string;
  score_home: number;
  score_away: number;
  finish: "reg" | "ot" | "so";
  khl_event_id?: number;
}

export interface Score {
  text: string;
  finish: "reg" | "ot" | "so";
}

// Приводим варианты названий к одному виду для матчинга счёта
export function normTeam(t: string): string {
  const k = (t || "").trim().toLowerCase();
  if (k === "драконы") return "шанхайские драконы";
  if (k === "динамо минск") return "динамо мн";
  if (k === "сочи") return "хк сочи";
  return k;
}

export function pairKey(a: string, b: string): string {
  return [normTeam(a), normTeam(b)].sort().join("|");
}

export function scoreFor(
  results: Record<string, ScoreResult>,
  home: string,
  away: string
): Score | null {
  const r = results[pairKey(home, away)];
  if (!r) return null;
  const text =
    normTeam(r.home) === normTeam(home)
      ? `${r.score_home} : ${r.score_away}`
      : `${r.score_away} : ${r.score_home}`;
  return { text, finish: r.finish };
}

export function buildResultsMap(list: ScoreResult[]): Record<string, ScoreResult> {
  const map: Record<string, ScoreResult> = {};
  for (const res of list) {
    map[pairKey(res.home, res.away)] = res;
  }
  return map;
}

export function eventIdFor(
  results: Record<string, ScoreResult>,
  home: string,
  away: string
): number | null {
  const r = results[pairKey(home, away)];
  return r?.khl_event_id ?? null;
}

export function finishLabel(finish: "reg" | "ot" | "so"): string | null {
  if (finish === "ot") return "ОТ";
  if (finish === "so") return "Б";
  return null;
}
