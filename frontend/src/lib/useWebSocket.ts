"use client";

import { useEffect, useRef, useCallback, useState } from "react";

export interface WsMatch {
  id: number;
  onhockey_id: string;
  league: string;
  team_home: string;
  team_away: string;
  datetime_utc: string;
  status: string;
  score: string | null;
  win_type: string | null;
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

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const ws = new WebSocket(`${protocol}//${host}/ws`);
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
