"use client";

import { useFavorites } from "@/lib/FavoritesContext";

interface FavoritesFilterProps {
  active: boolean;
  onToggle: () => void;
}

export default function FavoritesFilter({ active, onToggle }: FavoritesFilterProps) {
  const { favorites } = useFavorites();

  return (
    <button
      onClick={onToggle}
      disabled={!active && favorites.length === 0}
      className={`flex items-center gap-2 px-3 sm:px-5 py-2 sm:py-2.5 rounded-lg text-xs sm:text-sm font-semibold transition-all duration-200 flex-shrink-0 ${
        active
          ? "bg-hockey-accent text-white shadow-lg shadow-hockey-accent/20"
          : favorites.length === 0
          ? "bg-hockey-card border border-hockey-border text-hockey-text-muted opacity-50 cursor-not-allowed"
          : "bg-hockey-card border border-hockey-border text-hockey-text-secondary hover:text-white hover:border-hockey-border-light"
      }`}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill={active ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
      </svg>
      <span className="hidden sm:inline">Избранное</span>
      {favorites.length > 0 && (
        <span className="w-5 h-5 rounded-full bg-white/20 text-[10px] font-bold flex items-center justify-center">
          {favorites.length}
        </span>
      )}
    </button>
  );
}
