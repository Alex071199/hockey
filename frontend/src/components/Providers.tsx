"use client";

import { FavoritesProvider } from "@/lib/FavoritesContext";
import { ScoreToggleProvider } from "@/context/ScoreToggleContext";
import ToastContainer from "@/components/Toast";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <FavoritesProvider>
      <ScoreToggleProvider>
        {children}
        <ToastContainer />
      </ScoreToggleProvider>
    </FavoritesProvider>
  );
}
