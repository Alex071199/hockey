"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

export default function RemindButton({ className = "" }: { className?: string }) {
  const [open, setOpen] = useState(false);

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
  }, [open ]);

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
        Напоминание
      </button>
      {open &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          >
            <div
              className="glass rounded-2xl p-6 sm:p-8 max-w-xs w-full text-center"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="mx-auto mb-4 w-12 h-12 rounded-full bg-hockey-accent/10 border border-hockey-accent/30 flex items-center justify-center">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-hockey-accent">
                  <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
                  <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
                </svg>
              </div>
              <h3 className="text-base sm:text-lg font-bold mb-2">Напоминание</h3>
              <p className="text-xs sm:text-sm text-hockey-text-secondary mb-6">
                Функция скоро появится
              </p>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="btn-red w-full py-2.5 rounded-xl text-xs sm:text-sm font-bold"
              >
                <span className="relative z-10">Понятно</span>
              </button>
            </div>
          </div>,
          document.body
        )}
    </>
  );
}
