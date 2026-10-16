"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

declare global {
  interface Window {
    ym?: (...args: unknown[]) => void;
  }
}

const YM_ID = 113096901;

export default function YmTracker() {
  const pathname = usePathname();
  const lastUrlRef = useRef<string | null>(null);

  useEffect(() => {
    const url = window.location.href;
    if (lastUrlRef.current === url) return;
    if (typeof window.ym !== "function") return;
    lastUrlRef.current = url;
    window.ym(YM_ID, "hit", url);
  }, [pathname]);

  return null;
}
