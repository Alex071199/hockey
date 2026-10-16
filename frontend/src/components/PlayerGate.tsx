"use client";

import { useState } from "react";
import { getTeamLogo } from "@/lib/team-logos";

const AMOUNTS = [100, 200, 500, 1000];

interface PlayerGateProps {
  matchId: number;
  teamHome: string;
  teamAway: string;
  onWatch: () => void;
}

// Гейт перед плеером: стрим не маунтится, пока зритель не выберет
// «Смотреть» (запоминается на сутки) или не поддержит сервис донатом.
export default function PlayerGate({ matchId, teamHome, teamAway, onWatch }: PlayerGateProps) {
  const [step, setStep] = useState<"offer" | "donate">("offer");
  const [team, setTeam] = useState<string>(teamHome);
  const [amount, setAmount] = useState<number>(200);

  const pay = () => {
    window.dispatchEvent(
      new CustomEvent("hockey-open-payment", { detail: { team, amount, matchId } })
    );
  };

  const teams = [
    { name: teamHome, logo: getTeamLogo(teamHome) },
    { name: teamAway, logo: getTeamLogo(teamAway) },
  ];

  return (
    <div className="relative w-full min-h-[280px] sm:min-h-[360px] lg:min-h-[440px] overflow-hidden rounded-xl border border-hockey-border bg-gradient-to-b from-hockey-card via-black to-black">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(225,29,72,0.12),transparent_60%)]" aria-hidden />
      <div className="relative flex h-full min-h-[280px] sm:min-h-[360px] lg:min-h-[440px] flex-col items-center justify-center px-4 py-6 text-center">
        {step === "offer" ? (
          <div className="flex max-w-md flex-col items-center gap-3 sm:gap-4">
            <p className="text-[10px] sm:text-xs font-bold uppercase tracking-widest text-hockey-live">
              Трансляция готова к запуску
            </p>
            <h2 className="text-xl sm:text-3xl font-black tracking-tight">Поддержи сервис</h2>
            <p className="text-xs sm:text-sm leading-relaxed text-hockey-text-secondary">
              Hockey-Live работает без подписок и регистрации — его держат на донатах зрители.
              Поддержите — или просто включайте трансляцию.
            </p>
            <div className="flex w-full flex-col gap-2.5 pt-1 sm:flex-row">
              <button
                onClick={() => setStep("donate")}
                className="flex-1 rounded-xl bg-hockey-accent px-5 py-3 text-sm font-bold text-white transition-all hover:bg-hockey-accent/90 hover:shadow-lg hover:shadow-hockey-accent/25"
              >
                Поддержать
              </button>
              <button
                onClick={onWatch}
                className="flex-1 rounded-xl border border-hockey-border bg-hockey-card px-5 py-3 text-sm font-bold text-hockey-text-secondary transition-all hover:border-hockey-border-light hover:text-white"
              >
                Смотреть
              </button>
            </div>
            <p className="text-[10px] sm:text-[11px] text-hockey-text-muted">
              Выбор «Смотреть» действует сутки — гейт не появится снова
            </p>
          </div>
        ) : (
          <div className="flex w-full max-w-md flex-col items-center gap-3 sm:gap-4">
            <h2 className="text-lg sm:text-2xl font-black tracking-tight">Поддержать Hockey-Live</h2>

            <div className="flex w-full gap-2">
              {teams.map((t) => (
                <button
                  key={t.name}
                  onClick={() => setTeam(t.name)}
                  className={`flex flex-1 items-center justify-center gap-2 rounded-xl border-2 px-3 py-2.5 transition-all ${
                    team === t.name
                      ? "border-hockey-accent bg-hockey-accent/10"
                      : "border-hockey-border bg-hockey-card hover:border-hockey-border-light"
                  }`}
                >
                  {t.logo && <img src={t.logo} alt={t.name} className="h-5 w-5 object-contain" />}
                  <span className="truncate text-xs font-bold sm:text-sm">{t.name}</span>
                </button>
              ))}
            </div>

            <div className="flex w-full gap-2">
              {AMOUNTS.map((a) => (
                <button
                  key={a}
                  onClick={() => setAmount(a)}
                  className={`flex-1 rounded-lg py-2 text-sm font-bold transition-all ${
                    amount === a
                      ? "bg-hockey-accent text-white"
                      : "border border-hockey-border bg-hockey-card text-hockey-text-secondary hover:border-hockey-border-light"
                  }`}
                >
                  {a} ₽
                </button>
              ))}
            </div>

            <button
              onClick={pay}
              className="w-full rounded-xl bg-hockey-accent px-5 py-3 text-sm font-bold text-white transition-all hover:bg-hockey-accent/90 hover:shadow-lg hover:shadow-hockey-accent/25"
            >
              {`Перейти к оплате · ${amount} ₽`}
            </button>

            <div className="flex w-full gap-2">
              <button
                onClick={() => setStep("offer")}
                className="flex-1 rounded-xl border border-hockey-border bg-hockey-card px-4 py-2.5 text-xs font-bold text-hockey-text-muted transition-all hover:text-white"
              >
                ← Назад
              </button>
              <button
                onClick={onWatch}
                className="flex-1 rounded-xl border border-hockey-border bg-hockey-card px-4 py-2.5 text-xs font-bold text-hockey-text-secondary transition-all hover:border-hockey-border-light hover:text-white"
              >
                Смотреть
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
