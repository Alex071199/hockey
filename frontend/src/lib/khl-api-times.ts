const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export interface ApiKhlTime {
  home: string;
  away: string;
  date: string;
  time: string;
  start_utc?: string;
}

/** Fetch official start times for games starting within the next 72 hours. */
export async function fetchKhlUpcoming(): Promise<ApiKhlTime[]> {
  try {
    const res = await fetch(`${API_URL}/api/khl/upcoming`, { cache: "no-store" });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data?.matches) ? data.matches : [];
  } catch {
    return [];
  }
}
