"use client";

import { useState, useEffect, useRef, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
const SEEN_KEY = "hl_news_seen_id";

interface NewsItem {
  id: number;
  text: string;
  created_at: string | null;
}

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const created = new Date(iso);
  if (Number.isNaN(created.getTime())) return "";
  const diff = Math.floor((Date.now() - created.getTime()) / 1000);
  if (diff < 60) return "только что";
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`;
  if (diff < 172800) return "вчера";
  return created.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

export default function NotificationsBell() {
  const [news, setNews] = useState<NewsItem[]>([]);
  const [open, setOpen] = useState(false);
  const [seenId, setSeenId] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stored = Number(localStorage.getItem(SEEN_KEY) || 0);
    if (!Number.isNaN(stored)) setSeenId(stored);
  }, []);

  const load = useCallback(() => {
    fetch(`${API_URL}/api/news`)
      .then((r) => (r.ok ? r.json() : []))
      .then((items) => {
        if (Array.isArray(items)) setNews(items);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const unread = news.filter((n) => n.id > seenId).length;

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && news.length > 0) {
      const maxId = Math.max(...news.map((n) => n.id), seenId);
      setSeenId(maxId);
      localStorage.setItem(SEEN_KEY, String(maxId));
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        onClick={toggle}
        aria-label="Уведомления"
        title="Уведомления"
        className="relative w-9 h-9 flex items-center justify-center rounded-lg text-hockey-text-secondary hover:text-white hover:bg-white/5 transition-colors"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-hockey-accent text-white text-[10px] font-bold flex items-center justify-center">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-[320px] sm:w-[360px] max-h-[70vh] overflow-y-auto rounded-xl bg-hockey-card border border-hockey-border shadow-2xl shadow-black/60 animate-fade-in">
          <div className="px-4 py-3 border-b border-hockey-border flex items-center justify-between">
            <span className="text-sm font-bold text-white">Уведомления</span>
            {unread > 0 && (
              <span className="text-[11px] text-hockey-accent font-semibold">{unread} новых</span>
            )}
          </div>

          {news.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-hockey-text-secondary">
              Пока нет уведомлений
            </div>
          ) : (
            <ul>
              {news.map((n) => (
                <li
                  key={n.id}
                  className={`px-4 py-3 border-b border-hockey-border/60 last:border-b-0 ${
                    n.id > seenId ? "bg-hockey-accent/5" : ""
                  }`}
                >
                  <p className="text-sm text-white whitespace-pre-wrap break-words leading-relaxed">
                    {n.text}
                  </p>
                  <span className="block mt-1.5 text-[11px] text-hockey-text-secondary">
                    {timeAgo(n.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
