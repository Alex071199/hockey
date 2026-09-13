"use client";

import { useEffect, useRef } from "react";
import { showToast } from "./Toast";
import { parseMatchDate } from "@/lib/parse-date";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface Match {
  id: number;
  team_home: string;
  team_away: string;
  datetime_utc: string;
  status: string;
}

export default function MatchNotifications() {
  const notifiedRef = useRef<Set<number>>(new Set());
  const matchesRef = useRef<Match[]>([]);

  useEffect(() => {
    async function fetchMatches() {
      try {
        const res = await fetch(`${API_URL}/api/schedule`);
        if (res.ok) {
          matchesRef.current = await res.json();
        }
      } catch {}
    }
    fetchMatches();
    const fetchId = setInterval(fetchMatches, 5 * 60 * 1000);
    return () => clearInterval(fetchId);
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      matchesRef.current.forEach((match) => {
        if (match.status !== "pre_game") return;
        if (notifiedRef.current.has(match.id)) return;
        const matchTime = parseMatchDate(match.datetime_utc).getTime();
        const diff = matchTime - now;
        if (diff > 0 && diff <= 5 * 60 * 1000) {
          notifiedRef.current.add(match.id);
          showToast(`🏒 Матч начинается через 5 минут: ${match.team_home} — ${match.team_away}`);
          if ("Notification" in window && Notification.permission === "granted") {
            new Notification("HOCKEY LIVE", {
              body: `${match.team_home} — ${match.team_away} начинается через 5 минут`,
              icon: "/mainlogo.png",
            });
          }
        }
      });
    }, 15000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  return null;
}
