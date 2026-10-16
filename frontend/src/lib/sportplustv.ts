export interface Stream {
  url: string;
  quality: string;
  source: string;
}

const SP_DETAIL = "https://api.sportplustv.live/v5/matches/view";

function detectSource(url: string): string {
  if (url.includes("rutube")) return "rutube";
  if (url.includes("youtube") || url.includes("youtu.be")) return "youtube";
  if (url.includes("vk.com") || url.includes("vkvideo")) return "vk";
  return "sportplustv";
}

function collect(item: Record<string, any> | null | undefined): Stream[] {
  if (!item) return [];
  const out: Stream[] = [];
  const seen = new Set<string>();
  const add = (url: unknown) => {
    if (typeof url !== "string" || !url.startsWith("http") || seen.has(url)) return;
    seen.add(url);
    out.push({ url, quality: "auto", source: detectSource(url) });
  };

  const ls = item.ls;
  if (Array.isArray(ls)) ls.forEach(add);

  const tv = item.tv;
  if (Array.isArray(tv)) {
    tv.forEach((t: any) => add(typeof t === "object" && t ? t.url : t));
  }

  const sp = item.sp;
  if (Array.isArray(sp)) {
    sp.forEach((s: any) => add(typeof s === "object" && s ? s.url : s));
  }

  return out;
}

/**
 * SportPlusTV detail API отдаёт стримы только для РФ IP, поэтому бэкенд
 * (Railway, US) получает пустой список. Запрашиваем напрямую из браузера —
 * у API открытый CORS.
 */
export async function fetchSportPlusTVStreams(
  spMatchId: number,
  signal?: AbortSignal
): Promise<Stream[]> {
  const res = await fetch(`${SP_DETAIL}?id=${spMatchId}&lang=ru`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`SportPlusTV API ${res.status}`);
  const data = await res.json();
  return collect(data?.item);
}

/** Прямые m3u8-ссылки, которые нельзя отдавать через прокси (гео-блок). */
export function isDirectHls(url: string): boolean {
  return (
    url.includes("sportvideodata.com") ||
    url.includes("pppdata.com") ||
    url.includes("sportplustv.live")
  );
}
