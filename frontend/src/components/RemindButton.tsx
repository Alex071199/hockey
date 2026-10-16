"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
const STORAGE_KEY = "tg_reminder_code";

function getOrCreateCode(): string {
  try {
    const existing = localStorage.getItem(STORAGE_KEY);
    if (existing && /^[A-Za-z0-9_-]{8,64}$/.test(existing)) return existing;
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    const code = Array.from(bytes, (b) => b.toString(36).padStart(2, "0")).join("").slice(0, 32);
    localStorage.setItem(STORAGE_KEY, code);
    return code;
  } catch {
    return "fallbackcode12345678";
  }
}

interface Props {
  league: string;
  teamHome: string;
  teamAway: string;
  matchId?: number;
  datetimeUtc?: string;
  className?: string;
}

type State = "idle" | "creating" | "waiting" | "linked" | "error";

export default function RemindButton({
  league,
  teamHome,
  teamAway,
  matchId,
  datetimeUtc,
  className = "",
}: Props) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<State>("idle");
  const [deepLink, setDeepLink] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const create = useCallback(async () => {
    setState("creating");
    try {
      const code = getOrCreateCode();
      const res = await fetch(`${API_URL}/api/reminders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code,
          league,
          team_home: teamHome,
          team_away: teamAway,
          match_id: matchId ?? null,
          datetime_utc: datetimeUtc ?? null,
        }),
      });
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      setDeepLink(data.deep_link);
      setState(data.linked ? "linked" : "waiting");
      if (!data.linked) startPolling(code);
    } catch {
      setState("error");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [league, teamHome, teamAway, matchId, datetimeUtc]);

  const startPolling = useCallback(
    (code: string) => {
      stopPoll();
      pollRef.current = setInterval(async () => {
        try {
          const qs = new URLSearchParams({
            code,
            team_home: teamHome,
            team_away: teamAway,
          });
          const res = await fetch(`${API_URL}/api/reminders?${qs}`);
          const data = await res.json();
          if (data.linked) {
            stopPoll();
            setState("linked");
          }
        } catch {
          /* ignore */
        }
      }, 2500);
    },
    [teamHome, teamAway, stopPoll]
  );

  // status check — used both on mount (so the label survives F5) and on modal open
  const checkStatus = useCallback(async () => {
    try {
      const code = getOrCreateCode();
      const qs = new URLSearchParams({ code, team_home: teamHome, team_away: teamAway });
      const res = await fetch(`${API_URL}/api/reminders?${qs}`);
      const data = await res.json();
      if (data.linked) {
        setState("linked");
        stopPoll();
      } else if (data.exists) {
        setState((prev) => (prev === "creating" || prev === "error" ? prev : "waiting"));
        startPolling(code);
      }
      return data;
    } catch {
      return null;
    }
  }, [teamHome, teamAway, startPolling, stopPoll]);

  // restore state after page reload
  useEffect(() => {
    checkStatus();
  }, [checkStatus]);

  // check current status when modal opens
  useEffect(() => {
    if (!open) {
      stopPoll();
      return;
    }
    checkStatus();
    return stopPoll;
  }, [open, checkStatus, stopPoll]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open]);

  const remove = async () => {
    try {
      const code = getOrCreateCode();
      const qs = new URLSearchParams({ code, team_home: teamHome, team_away: teamAway });
      await fetch(`${API_URL}/api/reminders?${qs}`, { method: "DELETE" });
      setState("idle");
    } catch {
      /* ignore */
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen(true);
        }}
        className={`text-[10px] sm:text-xs font-bold px-2 sm:px-3 py-1 sm:py-1.5 rounded-lg transition-all duration-200 bg-white/5 text-hockey-text-secondary hover:bg-hockey-accent hover:text-white ${className}`}
      >
        {state === "linked" ? "Напоминание вкл." : "Напоминание"}
      </button>
      {open &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          >
            <div
              className="glass rounded-2xl p-6 sm:p-8 max-w-sm w-full text-center"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="mx-auto mb-4 w-12 h-12 rounded-full bg-hockey-accent/10 border border-hockey-accent/30 flex items-center justify-center">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-hockey-accent">
                  <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
                  <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
                </svg>
              </div>
              <h3 className="text-base sm:text-lg font-bold mb-1">Напоминание в Telegram</h3>
              <p className="text-xs sm:text-sm text-hockey-text-secondary mb-1 font-semibold">
                {teamHome} — {teamAway}
              </p>

              {state === "idle" && (
                <>
                  <p className="text-xs sm:text-sm text-hockey-text-secondary mb-5 mt-3">
                    Пришлём сообщение, когда матч появится в прямом эфире, со ссылкой на трансляцию.
                  </p>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      create();
                    }}
                    className="btn-red w-full py-2.5 rounded-xl text-xs sm:text-sm font-bold"
                  >
                    <span className="relative z-10">Включить напоминание</span>
                  </button>
                </>
              )}

              {state === "creating" && (
                <p className="text-xs sm:text-sm text-hockey-text-secondary my-6">Подключение…</p>
              )}

              {state === "waiting" && (
                <>
                  <p className="text-xs sm:text-sm text-hockey-text-secondary mb-4 mt-3">
                    Шаг 1. Откройте бота и нажмите <b>Start</b> — он свяжет сайт с вашим Telegram.
                  </p>
                  <a
                    href={deepLink}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-red block w-full py-2.5 rounded-xl text-xs sm:text-sm font-bold mb-3"
                  >
                    <span className="relative z-10">Открыть Telegram</span>
                  </a>
                  <p className="text-[11px] text-hockey-text-muted animate-pulse">
                    Ждём подтверждения в Telegram…
                  </p>
                </>
              )}

              {state === "linked" && (
                <>
                  <p className="text-xs sm:text-sm text-hockey-accent mb-5 mt-3 font-semibold">
                    ✓ Напоминание включено
                  </p>
                  <p className="text-[11px] text-hockey-text-muted mb-4">
                    Сообщение придёт в чат с ботом, когда матч начнётся.
                  </p>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.preventDefault();
                        remove();
                      }}
                      className="flex-1 py-2.5 rounded-xl text-xs sm:text-sm font-bold bg-white/5 text-hockey-text-secondary hover:bg-white/10 transition-colors"
                    >
                      Выключить
                    </button>
                    <button
                      type="button"
                      onClick={() => setOpen(false)}
                      className="btn-red flex-1 py-2.5 rounded-xl text-xs sm:text-sm font-bold"
                    >
                      <span className="relative z-10">Готово</span>
                    </button>
                  </div>
                </>
              )}

              {state === "error" && (
                <>
                  <p className="text-xs sm:text-sm text-hockey-text-secondary mb-5 mt-3">
                    Не удалось создать напоминание. Попробуйте ещё раз.
                  </p>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      create();
                    }}
                    className="btn-red w-full py-2.5 rounded-xl text-xs sm:text-sm font-bold"
                  >
                    <span className="relative z-10">Повторить</span>
                  </button>
                </>
              )}

              <button
                type="button"
                onClick={() => setOpen(false)}
                className="mt-3 w-full py-2 rounded-xl text-xs text-hockey-text-muted hover:text-hockey-text-secondary transition-colors"
              >
                Закрыть
              </button>
            </div>
          </div>,
          document.body
        )}
    </>
  );
}
