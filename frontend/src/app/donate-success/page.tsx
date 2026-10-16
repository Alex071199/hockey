"use client";

import { useEffect, useState } from "react";

export default function DonateSuccess() {
  const [inPopup, setInPopup] = useState<boolean | null>(null);

  useEffect(() => {
    const back = new URLSearchParams(window.location.search).get("back") || "/";
    if (window.opener && !window.opener.closed) {
      try {
        window.opener.postMessage({ type: "donation-success" }, "*");
      } catch {}
      setInPopup(true);
    } else {
      window.location.replace(back);
    }
  }, []);

  if (!inPopup) return null;

  return (
    <div className="min-h-screen bg-hockey-bg flex items-center justify-center px-4">
      <div className="glass rounded-2xl p-8 max-w-sm w-full text-center">
        <div className="text-4xl mb-4">🏒</div>
        <h1 className="text-xl font-black uppercase tracking-tight mb-2">Спасибо за донат!</h1>
        <p className="text-sm text-hockey-text-secondary mb-6">
          Ваш вклад поможет команде. Окно можно закрыть — матч остаётся открытым.
        </p>
        <button
          onClick={() => window.close()}
          className="w-full py-3 rounded-xl bg-hockey-accent text-white font-bold text-sm hover:bg-hockey-accent/90 transition-all"
        >
          Закрыть окно
        </button>
      </div>
    </div>
  );
}
