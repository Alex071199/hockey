"use client";

import { useEffect, useRef } from "react";
import { getTeamLogo } from "@/lib/team-logos";

interface Particle {
  x: number;
  y: number;
  speed: number;
  rotation: number;
  rotSpeed: number;
  size: number;
  opacity: number;
  logo: HTMLImageElement | null;
  text: string;
}

export default function DonationRain({
  team,
  amount,
  donor,
  message = "",
  duration = 7,
}: {
  team: string;
  amount: number;
  donor: string;
  message?: string;
  duration?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    const logoPath = getTeamLogo(team);
    let logo: HTMLImageElement | null = null;
    if (logoPath) {
      logo = new Image();
      logo.src = logoPath;
      logo.onerror = () => { logo = null; };
    }

    // плотность дождя растёт с суммой: 100₽→10, 200₽→15, 500₽→30, 1000₽→55
    const count = Math.min(150, Math.max(10, Math.round(5 + amount / 20)));
    // чем больше донат, тем быстрее падают логотипы
    const speedBoost = Math.min(4, amount / 1500);
    const particles: Particle[] = [];
    for (let i = 0; i < count; i++) {
      particles.push({
        x: Math.random() * canvas.width,
        y: -60 - Math.random() * canvas.height * 0.5,
        speed: 2 + Math.random() * 4 + speedBoost,
        rotation: Math.random() * Math.PI * 2,
        rotSpeed: (Math.random() - 0.5) * 0.1,
        size: 24 + Math.random() * 20,
        opacity: 1,
        logo,
        text: team,
      });
    }

    const start = performance.now();
    const durationMs = Math.max(3000, duration * 1000);

    const tick = (now: number) => {
      const elapsed = now - start;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const fadeStart = durationMs - 1500;
      const fade = elapsed > fadeStart ? 1 - (elapsed - fadeStart) / 1500 : 1;

      for (const p of particles) {
        p.y += p.speed;
        p.rotation += p.rotSpeed;
        if (p.y > canvas.height + 60) {
          p.y = -60;
          p.x = Math.random() * canvas.width;
        }

        ctx.save();
        ctx.globalAlpha = Math.max(0, fade * p.opacity);
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rotation);

        if (p.logo && p.logo.complete && p.logo.naturalWidth > 0) {
          ctx.drawImage(p.logo, -p.size / 2, -p.size / 2, p.size, p.size);
        } else {
          ctx.font = `bold ${Math.floor(p.size * 0.6)}px sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillStyle = "#fff";
          ctx.fillText(p.text, 0, 0);
        }
        ctx.restore();
      }

      if (elapsed < durationMs) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
      }
    };

    rafRef.current = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(rafRef.current);
      window.removeEventListener("resize", resize);
    };
  }, [team, amount, duration]);

  return (
    <>
      <canvas
        ref={canvasRef}
        className="fixed inset-0 z-20 pointer-events-none"
      />
      <div className="fixed top-20 left-1/2 -translate-x-1/2 z-50 pointer-events-none">
        <div className="glass rounded-2xl px-6 py-4 text-center animate-bounce">
          <p className="text-hockey-accent font-black text-lg">{donor}</p>
          <p className="text-white font-bold text-xl">{team}</p>
          <p className="text-hockey-text-secondary text-sm">{amount} ₽</p>
          {message && (
            <p className="mt-1 max-w-[260px] text-xs italic text-white/75 break-words">«{message}»</p>
          )}
        </div>
      </div>
    </>
  );
}
