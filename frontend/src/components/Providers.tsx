"use client";

import { FavoritesProvider } from "@/lib/FavoritesContext";
import ToastContainer from "@/components/Toast";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <FavoritesProvider>
      {children}
      <ToastContainer />
    </FavoritesProvider>
  );
}
