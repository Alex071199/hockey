"use client";

import { useEffect, useRef, useCallback, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export interface WsMatch {
  id: number;
  match_uid?: string;
  league: string;
  team_home: string;
  team_away: string;
  datetime_utc: string;
  status: string;
  home_score?: number | null;
  away_score?: number | null;
  current_period?: string | null;
  added_live?: boolean;
  stream_urls: { url: string; quality: string; source: string }[];
}

interface WsMessage {
  type: "matches_update" | "scores_update";
  data: WsMatch[];
}

export function useWebSocket(
  onMatchesUpdate: (matches: WsMatch[]) => void,
  onScoresUpdate: (matches: WsMatch[]) => void,
) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [connected, setConnected] = useState(false);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    // WS слушает бэкенд (Railway) — на Vercel /ws не существует
    const wsBase = API_URL.replace(/^http/, "ws"); // http→ws, https→wss
    const ws = new WebSocket(`${wsBase}/ws`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data);
        if (msg.type === "matches_update") onMatchesUpdate(msg.data);
        if (msg.type === "scores_update") onScoresUpdate(msg.data);
      } catch {}
    };

    ws.onclose = () => {
      setConnected(false);
      reconnectTimer.current = setTimeout(() => connect(), 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [onMatchesUpdate, onScoresUpdate]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected };
}
