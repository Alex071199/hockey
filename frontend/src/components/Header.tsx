"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export default function Header() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [hasLive, setHasLive] = useState(false);

  useEffect(() => {
    function checkLive() {
      fetch(`${API_URL}/api/schedule`)
        .then((r) => r.json())
        .then((matches) => {
          setHasLive(matches.some((m: { status: string }) => m.status === "live"));
        })
        .catch(() => {});
    }
    checkLive();
    const id = setInterval(checkLive, 30000);
    return () => clearInterval(id);
  }, []);

  const navLinks = [
    { href: "/", label: "Матчи" },
    { href: "/schedule", label: "Календарь" },
    { href: "/standings", label: "Таблица" },
    { href: "/donate", label: "Поддержать" },
  ];

  return (
    <header className="fixed top-0 left-0 right-0 z-50 glass">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14 sm:h-16">
          <Link href="/" className="flex items-center gap-2 sm:gap-3" onClick={() => setMenuOpen(false)}>
            <img src="/mainlogo.png" alt="HOCKEY LIVE" className="h-8 w-8 sm:h-9 sm:w-9 rounded-lg object-cover" />
            <span className="text-base sm:text-lg font-bold tracking-wider">
              HOCKEY<span className="text-hockey-accent"> LIVE</span>
            </span>
          </Link>

          <nav className="hidden md:flex items-center gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  pathname === link.href
                    ? "bg-white/10 text-white"
                    : "text-hockey-text-secondary hover:text-white hover:bg-white/5"
                }`}
              >
                {link.label}
              </Link>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <Link
              href="/#live"
              className="hidden sm:inline-flex btn-red px-4 py-2 rounded-lg text-xs font-bold items-center gap-2"
            >
              <span className="relative z-10">Смотреть</span>
              {hasLive && (
                <>
                  <span className="relative z-10">Live</span>
                  <span className="w-2 h-2 rounded-full bg-white animate-pulse-live relative z-10" />
                </>
              )}
            </Link>

            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="md:hidden w-9 h-9 flex items-center justify-center rounded-lg text-hockey-text-secondary hover:text-white hover:bg-white/5 transition-colors"
            >
              {menuOpen ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="3" y1="6" x2="21" y2="6" />
                  <line x1="3" y1="12" x2="21" y2="12" />
                  <line x1="3" y1="18" x2="21" y2="18" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>

      {menuOpen && (
        <div className="md:hidden border-t border-hockey-border bg-hockey-surface/95 backdrop-blur-xl">
          <div className="max-w-[1400px] mx-auto px-4 py-4 space-y-1">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMenuOpen(false)}
                className={`block px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200 ${
                  pathname === link.href
                    ? "bg-white/10 text-white"
                    : "text-hockey-text-secondary hover:text-white hover:bg-white/5"
                }`}
              >
                {link.label}
              </Link>
            ))}
            <Link
              href="/#live"
              onClick={() => setMenuOpen(false)}
              className="block px-4 py-3 rounded-lg text-sm font-bold btn-red text-center mt-2 items-center justify-center gap-2"
            >
              <span className="relative z-10">Смотреть матчи</span>
              {hasLive && (
                <>
                  <span className="relative z-10">Live</span>
                  <span className="w-2 h-2 rounded-full bg-white animate-pulse-live relative z-10" />
                </>
              )}
            </Link>
          </div>
        </div>
      )}
    </header>
  );
}
