import { Stream } from "./sportplustv";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export interface WinBroadcast {
  id: number;
  name: string;
  home: string;
  away: string;
  tournament: string;
  start_at?: number | null;
  /** hls — играем через наш прокси; embed — iframe-плеер (Twitch и т.п.) */
  stream?: { kind: "hls" | "embed"; url?: string } | null;
}

/**
 * Ищем live-матч в линии 1win с трансляцией по названиям команд.
 * Бэкенд сам ходит в WebSocket 1win и достаёт broadcast.url.
 */
export async function findWinBroadcast(
  home: string,
  away: string,
  datetimeUtc: string,
  signal?: AbortSignal
): Promise<WinBroadcast | null> {
  const qs = new URLSearchParams({ home, away });
  const date = (datetimeUtc || "").slice(0, 10);
  if (date) qs.set("date", date);
  const res = await fetch(`${API_URL}/api/broadcast/find?${qs.toString()}`, { signal });
  if (!res.ok) return null;
  const data = await res.json();
  return data && typeof data.id === "number" ? (data as WinBroadcast) : null;
}

/** URL всегда один и тот же — бэкенд сам обновляет подпись m3u8.
 *  Для iframe-источников (Twitch) отдаём сам embed-адрес. */
export function winStream(broadcast: WinBroadcast): Stream {
  if (broadcast.stream?.kind === "embed" && broadcast.stream.url) {
    return { url: broadcast.stream.url, quality: "auto", source: "prime" };
  }
  return {
    url: `${API_URL}/api/broadcast/${broadcast.id}/stream.m3u8`,
    quality: "auto",
    source: "prime",
  };
}
