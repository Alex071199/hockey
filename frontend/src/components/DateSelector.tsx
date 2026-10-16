"use client";

import { useMemo, useRef, useEffect } from "react";
import { useKhlCalendar } from "@/lib/khl-calendar";

interface DateSelectorProps {
  selected: string;
  onSelect: (date: string) => void;
}

function fallbackDates(): string[] {
  const out: string[] = [];
  const base = new Date();
  for (let d = -7; d <= 60; d++) {
    const x = new Date(base.getFullYear(), base.getMonth(), base.getDate() + d);
    out.push(
      `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`
    );
  }
  return out;
}

export default function DateSelector({ selected, onSelect }: DateSelectorProps) {
  const { matches: calendar } = useKhlCalendar();
  const allDates = useMemo(() => {
    const set = new Set<string>();
    for (const m of calendar) set.add(m.date);
    return set.size > 0 ? Array.from(set).sort() : fallbackDates();
  }, [calendar]);
  const scrollRef = useRef<HTMLDivElement>(null);

  const surroundingDates = useMemo(() => {
    const idx = allDates.indexOf(selected);
    if (idx !== -1) {
      const start = Math.max(0, idx - 7);
      const end = Math.min(allDates.length, idx + 8);
      return allDates.slice(start, end);
    }
    const todayStr = new Date().toISOString().split("T")[0];
    let nearestIdx = 0;
    let minDiff = Infinity;
    for (let i = 0; i < allDates.length; i++) {
      const diff = Math.abs(new Date(allDates[i]).getTime() - new Date(todayStr).getTime());
      if (diff < minDiff) { minDiff = diff; nearestIdx = i; }
    }
    const start = Math.max(0, nearestIdx - 7);
    const end = Math.min(allDates.length, nearestIdx + 8);
    return allDates.slice(start, end);
  }, [allDates, selected]);

  useEffect(() => {
    if (!scrollRef.current) return;
    const container = scrollRef.current;
    const activeBtn = container.querySelector<HTMLElement>("[data-active='true']");
    if (activeBtn) {
      const containerWidth = container.offsetWidth;
      const btnLeft = activeBtn.offsetLeft;
      const btnWidth = activeBtn.offsetWidth;
      container.scrollTo({ left: btnLeft - containerWidth / 2 + btnWidth / 2, behavior: "smooth" });
    }
  }, [surroundingDates]);

  const canGoBack = surroundingDates[0] !== allDates[0];
  const canGoForward = surroundingDates[surroundingDates.length - 1] !== allDates[allDates.length - 1];

  function shiftDay(dateStr: string, delta: number): string {
    const d = new Date(dateStr + "T00:00:00");
    d.setDate(d.getDate() + delta);
    const y = d.getFullYear();
    const m = (d.getMonth() + 1).toString().padStart(2, "0");
    const day = d.getDate().toString().padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function goBack() {
    const idx = allDates.indexOf(selected);
    if (idx > 0) onSelect(allDates[idx - 1]);
    else if (idx === -1) onSelect(shiftDay(selected, -1));
  }

  function goForward() {
    const idx = allDates.indexOf(selected);
    if (idx >= 0 && idx < allDates.length - 1) onSelect(allDates[idx + 1]);
    else if (idx === -1) onSelect(shiftDay(selected, 1));
  }

  function formatShort(dateStr: string): string {
    const d = new Date(dateStr + "T00:00:00");
    const day = d.getDate().toString().padStart(2, "0");
    const month = (d.getMonth() + 1).toString().padStart(2, "0");
    return `${day}.${month}`;
  }

  function dayName(dateStr: string): string {
    const d = new Date(dateStr + "T00:00:00");
    return ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"][d.getDay()];
  }

  function isToday(dateStr: string): boolean {
    const today = new Date().toISOString().split("T")[0];
    return dateStr === today;
  }

  return (
    <div className="flex items-center gap-1.5 sm:gap-2">
      <button
        onClick={goBack}
        disabled={!canGoBack}
        className="flex-shrink-0 w-8 h-8 sm:w-9 sm:h-9 rounded-lg flex items-center justify-center bg-hockey-card border border-hockey-border text-hockey-text-secondary hover:text-white hover:border-hockey-border-light transition-all disabled:opacity-30 disabled:cursor-not-allowed"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>

      <div ref={scrollRef} className="flex gap-1.5 sm:gap-2 overflow-x-auto pb-1 scrollbar-hide">
        {surroundingDates.map((dateStr) => {
          const active = selected === dateStr;
          const today = isToday(dateStr);
          return (
            <button
              key={dateStr}
              data-active={active ? "true" : undefined}
              onClick={() => onSelect(dateStr)}
              className={`flex-shrink-0 px-3 sm:px-4 py-2 sm:py-2.5 rounded-xl text-center transition-all duration-200 min-w-[60px] sm:min-w-[72px] ${
                active
                  ? "bg-hockey-accent text-white shadow-lg shadow-hockey-accent/20"
                  : today
                  ? "bg-hockey-card border-2 border-hockey-accent/40 text-white"
                  : "bg-hockey-card border border-hockey-border text-hockey-text-secondary hover:border-hockey-border-light hover:text-white"
              }`}
            >
              <div className="text-[9px] sm:text-[10px] font-medium opacity-70">{dayName(dateStr)}</div>
              <div className="text-xs sm:text-sm font-bold mt-0.5">{formatShort(dateStr)}</div>
            </button>
          );
        })}
      </div>

      <button
        onClick={goForward}
        disabled={!canGoForward}
        className="flex-shrink-0 w-8 h-8 sm:w-9 sm:h-9 rounded-lg flex items-center justify-center bg-hockey-card border border-hockey-border text-hockey-text-secondary hover:text-white hover:border-hockey-border-light transition-all disabled:opacity-30 disabled:cursor-not-allowed"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </button>
    </div>
  );
}
