"use client";

import { createContext, useContext, useState, useCallback, useEffect } from "react";

type ScoreToggleContextType = {
  showScores: boolean;
  toggleScores: () => void;
};

const ScoreToggleContext = createContext<ScoreToggleContextType>({
  showScores: true,
  toggleScores: () => {},
});

const STORAGE_KEY = "hockey_show_scores";

function getStored(): boolean {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "false" ? false : true;
  } catch {
    return true;
  }
}

export function ScoreToggleProvider({ children }: { children: React.ReactNode }) {
  const [showScores, setShowScores] = useState(getStored);

  const toggleScores = useCallback(() => {
    setShowScores((v) => {
      const next = !v;
      try { localStorage.setItem(STORAGE_KEY, String(next)); } catch {}
      return next;
    });
  }, []);

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, String(showScores)); } catch {}
  }, [showScores]);

  return (
    <ScoreToggleContext.Provider value={{ showScores, toggleScores }}>
      {children}
    </ScoreToggleContext.Provider>
  );
}

export function useScoreToggle() {
  return useContext(ScoreToggleContext);
}
