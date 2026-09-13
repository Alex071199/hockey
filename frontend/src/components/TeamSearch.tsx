"use client";

import { useState, useRef, useEffect } from "react";
import { getTeamLogo } from "@/lib/team-logos";

interface TeamSearchProps {
  teams: string[];
  onSelect: (team: string) => void;
}

export default function TeamSearch({ teams, onSelect }: TeamSearchProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const filtered = query.trim()
    ? teams.filter((t) => typeof t === "string" && t.toLowerCase().includes(query.toLowerCase()))
    : [];

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div ref={ref} className="relative w-full sm:w-72">
      <label className="block text-xs font-semibold text-hockey-accent mb-1.5 uppercase tracking-wider">Поиск команды</label>
      <div className="relative">
        <svg
          className="absolute left-3 top-1/2 -translate-y-1/2 text-hockey-accent"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          placeholder="Введите название..."
          className="w-full pl-10 pr-4 py-3 rounded-xl bg-hockey-card border-2 border-hockey-accent/40 text-sm text-white placeholder:text-hockey-text-secondary focus:outline-none focus:border-hockey-accent focus:ring-2 focus:ring-hockey-accent/20 transition-all"
        />
        {query && (
          <button
            onClick={() => { setQuery(""); setOpen(false); onSelect(""); }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-hockey-text-muted hover:text-white"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        )}
      </div>

      {open && filtered.length > 0 && (
        <div className="absolute z-50 mt-2 w-full bg-hockey-card border-2 border-hockey-accent/30 rounded-xl shadow-xl max-h-60 overflow-y-auto">
          {filtered.map((team) => (
            <button
              key={team}
              onClick={() => { setQuery(team); setOpen(false); onSelect(team); }}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-hockey-accent/10 transition-colors text-left border-b border-hockey-border last:border-0"
            >
              {getTeamLogo(team) && (
                <img src={getTeamLogo(team)!} alt={team} className="w-6 h-6 object-contain" />
              )}
              <span className="text-sm text-white font-medium">{team}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
