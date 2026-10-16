"use client";

import { useEffect, useState } from "react";
import { getTeamLogo } from "@/lib/team-logos";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
const CLOUDTIPS_ORIGIN = "https://pay.cloudtips.ru";
const CLOUDTIPS_PAGE = "00cb8ffe";

const AMOUNTS = [100, 200, 500, 1000];

interface DonateButtonsProps {
  matchId: number;
  teamHome: string;
  teamAway: string;
  league: string;
}

interface ScoreSide {
  name: string;
  amount: number;
}
interface DonationScore {
  home: ScoreSide;
  away: ScoreSide;
}

interface Payment {
  team: string;
  amount: number;
  url: string;
}

export default function DonateButtons({ matchId, teamHome, teamAway, league }: DonateButtonsProps) {
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null);
  const [selectedAmount, setSelectedAmount] = useState<number>(100);
  const [showAmounts, setShowAmounts] = useState(false);
  const [payment, setPayment] = useState<Payment | null>(null);
  const [payStatus, setPayStatus] = useState<"paying" | "success" | "fail">("paying");
  const [score, setScore] = useState<DonationScore | null>(null);
  const [successInfo, setSuccessInfo] = useState<{ donor: string; message: string } | null>(null);

  // соревнование болельщиков: суммы по сторонам + события оплаты
  useEffect(() => {
    if (!matchId) return;
    let stopped = false;
    const load = () => {
      fetch(`${API_URL}/api/donations/score/${matchId}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (!stopped && d && d.home && d.away) setScore(d);
        })
        .catch(() => {});
    };
    load();
    const timer = setInterval(load, 15000);
    const onMessage = (e: MessageEvent) => {
      if (e.data && e.data.type === "donation-success") {
        load();
        return;
      }
      // CloudTips шлёт события виджета в родительское окно при siteOrigin
      if (e.origin !== CLOUDTIPS_ORIGIN || !payment) return;
      const m = e.data;
      if (!m || typeof m.siteWidgetMessage !== "string") return;
      if (m.siteWidgetMessage === "success") {
        const d = (m.data || {}) as {
          transactionId?: unknown;
          identifier?: unknown;
          name?: unknown;
          comment?: unknown;
        };
        const tx = String(d.transactionId ?? d.identifier ?? "");
        const donorName = typeof d.name === "string" ? d.name.trim().slice(0, 50) : "";
        const comment = typeof d.comment === "string" ? d.comment.trim().slice(0, 200) : "";
        fetch(`${API_URL}/api/donations/confirm`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            match_id: matchId,
            team: payment.team,
            amount: payment.amount,
            tx_id: tx,
            donor_name: donorName,
            message: comment,
          }),
        })
          .then(() => load())
          .catch(() => {});
        setSuccessInfo({ donor: donorName, message: comment });
        setPayStatus("success");
        // гейт перед плеером закрывается после успешного доната
        window.dispatchEvent(new CustomEvent("hockey-donation-success"));
        window.setTimeout(() => setPayment(null), 3500);
      } else if (m.siteWidgetMessage === "fail") {
        setPayStatus("fail");
      }
    };
    window.addEventListener("message", onMessage);
    return () => {
      stopped = true;
      clearInterval(timer);
      window.removeEventListener("message", onMessage);
    };
  }, [matchId, payment]);

  useEffect(() => {
    if (!payment) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPayment(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [payment]);

  const closePayment = () => setPayment(null);

  const buildPaymentUrl = (team: string, amount: number) => {
    const origin = window.location.origin;
    const info = JSON.stringify({ src: "hockeylive", match: matchId, team });
    // siteOrigin — включает postMessage виджета (init/success/fail) в эту вкладку;
    // hideamount — сумма фиксируется нашим выбором, зрителю нечего менять
    return (
      `${CLOUDTIPS_ORIGIN}/p/${CLOUDTIPS_PAGE}?amount=${amount}` +
      `&hideamount=true&siteOrigin=${encodeURIComponent(origin)}` +
      `&info=${encodeURIComponent(info)}`
    );
  };

  // гейт перед плеером просит открыть оплату сразу с выбранными суммой/командой
  useEffect(() => {
    const onOpen = (e: Event) => {
      const d = (e as CustomEvent).detail as { matchId?: number; team?: string; amount?: number };
      if (d.matchId !== matchId || !d.team || !d.amount) return;
      setSelectedTeam(d.team);
      setSelectedAmount(d.amount);
      setPayStatus("paying");
      setSuccessInfo(null);
      setPayment({ team: d.team, amount: d.amount, url: buildPaymentUrl(d.team, d.amount) });
    };
    window.addEventListener("hockey-open-payment", onOpen);
    return () => window.removeEventListener("hockey-open-payment", onOpen);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchId]);

  const handleDonate = () => {
    if (!selectedTeam) return;
    setPayStatus("paying");
    setSuccessInfo(null);
    setPayment({ team: selectedTeam, amount: selectedAmount, url: buildPaymentUrl(selectedTeam, selectedAmount) });
  };

  const teams = [
    { name: teamHome, logo: getTeamLogo(teamHome) },
    { name: teamAway, logo: getTeamLogo(teamAway) },
  ];

  const totalAmount = score ? score.home.amount + score.away.amount : 0;
  const homePct = totalAmount > 0 ? Math.round((score!.home.amount / totalAmount) * 100) : 50;
  const awayPct = totalAmount > 0 ? 100 - homePct : 50;

  const scoreRow = (side: ScoreSide, pct: number, barColor: string) => (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-2 min-w-0">
        {getTeamLogo(side.name) && (
          <img src={getTeamLogo(side.name)!} alt={side.name} className="w-5 h-5 object-contain" />
        )}
        <span className="text-xs sm:text-sm font-bold truncate">{side.name}</span>
      </div>
      <span className="text-xs sm:text-sm font-black tabular-nums" style={{ color: barColor }}>
        {side.amount} ₽{totalAmount > 0 && <span className="text-hockey-text-muted font-bold"> · {pct}%</span>}
      </span>
    </div>
  );

  return (
    <div className="mt-4">
      <div className="mb-4">
        <p className="text-[10px] sm:text-xs text-hockey-text-muted mb-2 uppercase tracking-wider font-bold">
          Соревнование болельщиков
        </p>
        <div className="rounded-xl border border-hockey-border bg-hockey-card p-3 space-y-2">
          {score && scoreRow(score.home, homePct, "#e11d48")}
          <div className="flex h-3 rounded-full overflow-hidden bg-hockey-border" aria-hidden>
            {totalAmount > 0 && (
              <>
                <div
                  className="bg-hockey-accent transition-all duration-700"
                  style={{ width: `${homePct}%` }}
                />
                <div className="bg-white transition-all duration-700" style={{ width: `${awayPct}%` }} />
              </>
            )}
          </div>
          {score && scoreRow(score.away, awayPct, "#ffffff")}
          {score && totalAmount === 0 && (
            <p className="text-[10px] text-hockey-text-muted text-center pt-1">
              Донатов пока нет — станьте первым
            </p>
          )}
        </div>
      </div>

      <p className="text-[10px] sm:text-xs text-hockey-text-muted mb-2 uppercase tracking-wider font-bold">
        Поддержать команду
      </p>
      <div className="flex gap-2">
        {teams.map((t) => (
          <button
            key={t.name}
            onClick={() => {
              setSelectedTeam(t.name);
              setShowAmounts(true);
            }}
            className={`flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl border-2 transition-all ${
              selectedTeam === t.name
                ? "border-hockey-accent bg-hockey-accent/10"
                : "border-hockey-border hover:border-hockey-border-light bg-hockey-card"
            }`}
          >
            {t.logo && (
              <img src={t.logo} alt={t.name} className="w-5 h-5 object-contain" />
            )}
            <span className="text-xs sm:text-sm font-bold truncate">{t.name}</span>
          </button>
        ))}
      </div>

      {showAmounts && selectedTeam && (
        <div className="mt-3">
          <div className="flex gap-2 mb-3">
            {AMOUNTS.map((a) => (
              <button
                key={a}
                onClick={() => setSelectedAmount(a)}
                className={`flex-1 py-2 rounded-lg text-sm font-bold transition-all ${
                  selectedAmount === a
                    ? "bg-hockey-accent text-white"
                    : "bg-hockey-card border border-hockey-border text-hockey-text-secondary hover:border-hockey-border-light"
                }`}
              >
                {a} ₽
              </button>
            ))}
          </div>
          <button
            onClick={handleDonate}
            className="w-full py-3 rounded-xl bg-hockey-accent text-white font-bold text-sm hover:bg-hockey-accent/90 transition-all"
          >
            {`Поддержать ${selectedTeam} на ${selectedAmount} ₽`}
          </button>
          <div className="mt-3 rounded-xl border border-hockey-border bg-hockey-card p-3">
            <p className="text-[10px] text-hockey-text-muted mb-2 uppercase tracking-wider font-bold text-center">
              Что будет после доната
            </p>
            <ul className="space-y-1.5 text-[11px] leading-snug text-hockey-text-secondary">
              <li className="flex items-start gap-2">
                <span className="text-hockey-accent font-black shrink-0">✓</span>
                <span>Дождь из логотипов вашей команды поверх трансляции — дольше с ростом суммы</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-hockey-accent font-black shrink-0">✓</span>
                <span>Ваше имя и сообщение увидят зрители этого матча</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-hockey-accent font-black shrink-0">✓</span>
                <span>Донат засчитается в соревнование болельщиков</span>
              </li>
            </ul>
            <p className="text-[10px] text-hockey-text-muted mt-2.5 text-center">
              Оплата картой через CloudTips — откроется прямо здесь, страница останется открытой
            </p>
          </div>
        </div>
      )}

      {payment && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/85 p-3 sm:p-6"
          onClick={closePayment}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="flex h-[90vh] sm:h-[85vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex h-11 shrink-0 items-center justify-between bg-hockey-card px-3">
              <span className="text-xs font-bold text-white truncate">
                Донат · {payment.team} · {payment.amount} ₽
              </span>
              <button
                onClick={closePayment}
                aria-label="Закрыть"
                className="ml-3 w-7 h-7 flex items-center justify-center rounded-lg text-hockey-text-muted hover:text-white hover:bg-hockey-border transition-colors"
              >
                ✕
              </button>
            </div>

            {payStatus === "success" ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center bg-white">
                <div className="w-14 h-14 rounded-full bg-emerald-500/10 flex items-center justify-center">
                  <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 6L9 17l-5-5" />
                  </svg>
                </div>
                <p className="text-lg font-black text-neutral-900">Спасибо за поддержку!</p>
                {successInfo && (successInfo.donor || successInfo.message) && (
                  <div className="max-w-sm space-y-1">
                    {successInfo.donor && (
                      <p className="text-sm font-bold text-neutral-700">{successInfo.donor}</p>
                    )}
                    {successInfo.message && (
                      <p className="text-xs italic text-neutral-500 break-words">«{successInfo.message}»</p>
                    )}
                  </div>
                )}
                <p className="text-sm text-neutral-500">
                  Ваш донат учтён в соревновании болельщиков
                </p>
                <p className="text-xs text-neutral-400">
                  Дождь из логотипов уже летит — не закрывайте страницу
                </p>
              </div>
            ) : payStatus === "fail" ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6 text-center bg-white">
                <div className="w-14 h-14 rounded-full bg-red-500/10 flex items-center justify-center">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                </div>
                <p className="text-lg font-black text-neutral-900">Оплата не прошла</p>
                <button
                  onClick={() => setPayStatus("paying")}
                  className="px-6 py-2.5 rounded-xl bg-hockey-accent text-white font-bold text-sm hover:bg-hockey-accent/90 transition-all"
                >
                  Попробовать снова
                </button>
              </div>
            ) : (
              <iframe
                src={payment.url}
                title="Оплата доната"
                allow="payment"
                className="min-h-0 w-full flex-1 border-0 bg-white"
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
