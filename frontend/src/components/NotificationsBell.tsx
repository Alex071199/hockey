"use client";

import { useState, useEffect, useRef, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
const SEEN_KEY = "hl_news_seen_id";
const SEEN_AT_KEY = "hl_news_seen_at";

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
  const [seenAt, setSeenAt] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stored = Number(localStorage.getItem(SEEN_KEY) || 0);
    if (!Number.isNaN(stored)) setSeenId(stored);
    // миграция: раньше просмотр считался по id новости, теперь по времени
    const at = Number(localStorage.getItem(SEEN_AT_KEY) || 0);
    if (at > 0) {
      setSeenAt(at);
    } else if (!Number.isNaN(stored) && stored > 0) {
      const now = Date.now();
      setSeenAt(now);
      localStorage.setItem(SEEN_AT_KEY, String(now));
    }
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

  // id > seenId — запас на случай, если id вдруг начнутся заново;
  // created_at > seenAt — надёжный признак «новое после последнего просмотра»
  const isNew = (n: NewsItem) =>
    n.id > seenId || (!!n.created_at && Date.parse(n.created_at) > seenAt);

  const unread = news.filter(isNew).length;

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && news.length > 0) {
      const maxId = Math.max(...news.map((n) => n.id), seenId);
      // считаем просмотренным всё, что уже показано, даже если часы
      // браузера и сервера немного расходятся
      const maxCreated = news.reduce(
        (m, n) => Math.max(m, n.created_at ? Date.parse(n.created_at) || 0 : 0),
        0
      );
      const nextSeenAt = Math.max(Date.now(), maxCreated);
      setSeenId(maxId);
      setSeenAt(nextSeenAt);
      localStorage.setItem(SEEN_KEY, String(maxId));
      localStorage.setItem(SEEN_AT_KEY, String(nextSeenAt));
      // сервер помечает просмотренными — через 24 часа они удалятся
      fetch(`${API_URL}/api/news/seen`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_id: maxId }),
      }).catch(() => {});
    }
  }

  function remove(id: number, e: React.MouseEvent) {
    e.stopPropagation();
    setNews((prev) => prev.filter((n) => n.id !== id));
    fetch(`${API_URL}/api/news/${id}`, { method: "DELETE" }).catch(() => {});
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
                  className={`relative px-4 pr-9 py-3 border-b border-hockey-border/60 last:border-b-0 ${
                    isNew(n) ? "bg-hockey-accent/5" : ""
                  }`}
                >
                  <p className="text-sm text-white whitespace-pre-wrap break-words leading-relaxed">
                    {n.text}
                  </p>
                  <span className="block mt-1.5 text-[11px] text-hockey-text-secondary">
                    {timeAgo(n.created_at)}
                  </span>
                  <button
                    onClick={(e) => remove(n.id, e)}
                    aria-label="Удалить уведомление"
                    title="Удалить"
                    className="absolute top-2 right-2 w-6 h-6 flex items-center justify-center rounded-md text-hockey-text-muted hover:text-white hover:bg-white/10 transition-colors"
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                      <path d="M18 6 6 18M6 6l12 12" />
                    </svg>
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="h-2 bg-hockey-border/70 border-t border-hockey-border" />
          <a
            href="https://t.me/hockeylivenotificationbot"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2.5 px-4 py-3 text-sm text-hockey-text-secondary hover:text-white hover:bg-white/5 transition-colors"
          >
            <svg width="18" height="18" viewBox="0 0 256 256" preserveAspectRatio="xMidYMid" aria-hidden="true">
              <defs>
                <linearGradient id="tlg-a" x1="50%" x2="50%" y1="0%" y2="100%">
                  <stop offset="0%" stopColor="#2AABEE" />
                  <stop offset="100%" stopColor="#229ED9" />
                </linearGradient>
              </defs>
              <path fill="url(#tlg-a)" d="M128 0C94.06 0 61.48 13.494 37.5 37.49A128.038 128.038 0 0 0 0 128c0 33.934 13.5 66.514 37.5 90.51C61.48 242.506 94.06 256 128 256s66.52-13.494 90.5-37.49c24-23.996 37.5-56.576 37.5-90.51 0-33.934-13.5-66.514-37.5-90.51C194.52 13.494 161.94 0 128 0Z" />
              <path fill="#FFF" d="M57.94 126.648c37.32-16.256 62.2-26.974 74.64-32.152 35.56-14.786 42.94-17.354 47.76-17.441 1.06-.017 3.42.245 4.96 1.49 1.28 1.05 1.64 2.47 1.82 3.467.16.996.38 3.266.2 5.038-1.92 20.24-10.26 69.356-14.5 92.026-1.78 9.592-5.32 12.808-8.74 13.122-7.44.684-13.08-4.912-20.28-9.63-11.26-7.386-17.62-11.982-28.56-19.188-12.64-8.328-4.44-12.906 2.76-20.386 1.88-1.958 34.64-31.748 35.26-34.45.08-.338.16-1.598-.6-2.262-.74-.666-1.84-.438-2.64-.258-1.14.256-19.12 12.152-54 35.686-5.1 3.508-9.72 5.218-13.88 5.128-4.56-.098-13.36-2.584-19.9-4.708-8-2.606-14.38-3.984-13.82-8.41.28-2.304 3.46-4.662 9.52-7.072Z" />
            </svg>
            <span>Наш Telegram-бот</span>
          </a>
        </div>
      )}
    </div>
  );
}
