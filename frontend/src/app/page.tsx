import { Suspense } from "react";
import MatchCard from "@/components/MatchCard";
import Link from "next/link";
import { khlCalendar } from "@/data/khl-calendar";
import { getTeamLogo } from "@/lib/team-logos";
import { parseMatchDate } from "@/lib/parse-date";
import MatchNotifications from "@/components/MatchNotifications";
import LiveSectionClient from "@/components/LiveSectionClient";

export const dynamic = "force-dynamic";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface Match {
  id: number;
  match_uid: string;
  league: string;
  team_home: string;
  team_away: string;
  datetime_utc: string;
  status: string;
  stream_urls: { url: string; quality: string; source: string }[];
}

async function getTodayMatches(): Promise<Match[]> {
  try {
    const response = await fetch(`${API_URL}/api/schedule`, {
      cache: "no-store",
    });
    if (!response.ok) return [];
    return response.json();
  } catch {
    return [];
  }
}

function getNextKhlMatch() {
  const now = new Date();
  return khlCalendar.find((m) => {
    const [h, min] = m.time.split(":").map(Number);
    const utcMs = Date.UTC(
      parseInt(m.date.slice(0, 4)),
      parseInt(m.date.slice(5, 7)) - 1,
      parseInt(m.date.slice(8, 10)),
      h, min, 0
    ) - 3 * 60 * 60 * 1000;
    return new Date(utcMs) > now;
  }) || null;
}

async function HeroSection() {
  const matches = await getTodayMatches();
  // В первом блоке — игра, начавшаяся последней
  const liveMatch = matches
    .filter((m) => m.status === "live")
    .sort((a, b) => parseMatchDate(b.datetime_utc).getTime() - parseMatchDate(a.datetime_utc).getTime())[0];
  const nextKhl = !liveMatch ? getNextKhlMatch() : null;

  return (
    <section className="relative min-h-[70vh] sm:h-[85vh] sm:min-h-[600px] flex items-start sm:items-center arena-bg overflow-hidden">
      <div className="relative z-10 max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 w-full pt-24 pb-12 sm:pt-0 sm:pb-0">
        <div className="grid lg:grid-cols-2 gap-6 sm:gap-12 items-center">
          <div className="animate-fade-in">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-hockey-accent/10 border border-hockey-accent/20 mb-4 sm:mb-6">
              <span className="w-2 h-2 rounded-full bg-hockey-accent animate-pulse-live" />
              <span className="text-[10px] sm:text-xs font-semibold text-hockey-accent tracking-wider uppercase">Прямой эфир</span>
            </div>

            <h1 className="text-4xl sm:text-5xl lg:text-7xl font-black tracking-tight leading-none mb-4 sm:mb-6">
              <span className="ice-text">ХОККЕЙ.</span>
              <br />
              <span className="text-hockey-accent">В ПРЯМОМ</span>
              <br />
              <span className="ice-text">ЭФИРЕ.</span>
            </h1>

            <p className="text-base sm:text-lg text-hockey-text-secondary mb-6 sm:mb-8 max-w-md">
              Смотри матчи там, где тебе удобно
            </p>

            <div className="flex flex-wrap gap-3 sm:gap-4">
              <Link
                href="#live"
                className="btn-red px-6 sm:px-8 py-3 sm:py-4 rounded-xl text-sm sm:text-base font-bold"
              >
                <span className="relative z-10">Смотреть матчи</span>
              </Link>
              <Link
                href="/schedule"
                className="px-6 sm:px-8 py-3 sm:py-4 rounded-xl text-sm sm:text-base font-medium border border-hockey-border text-hockey-text-secondary hover:text-white hover:border-hockey-text-muted transition-all duration-200"
              >
                Календарь
              </Link>
            </div>
          </div>

          {liveMatch ? (
            <div className="animate-fade-in" style={{ animationDelay: "0.2s" }}>
              <div className="glass rounded-2xl p-4 sm:p-6 max-w-md mx-auto lg:ml-auto">
                <div className="flex items-center gap-2 mb-3 sm:mb-4">
                  <span className="w-2.5 h-2.5 rounded-full bg-hockey-live animate-pulse-live" />
                  <span className="text-[10px] sm:text-xs font-bold text-hockey-live tracking-wider uppercase">Сейчас в эфире</span>
                </div>
                <div className="flex items-center justify-between gap-2 sm:gap-4 mb-3 sm:mb-4">
                  <div className="flex-1 flex items-center justify-end gap-2 sm:gap-3">
                    <p className="text-sm sm:text-lg font-bold text-right">{liveMatch.team_home}</p>
                    {getTeamLogo(liveMatch.team_home) && (
                      <img src={getTeamLogo(liveMatch.team_home)!} alt={liveMatch.team_home} className="w-9 h-9 sm:w-12 sm:h-12 object-contain" />
                    )}
                  </div>
                  <span className="text-[10px] sm:text-xs font-black text-hockey-text-muted">VS</span>
                  <div className="flex-1 flex items-center gap-2 sm:gap-3">
                    {getTeamLogo(liveMatch.team_away) && (
                      <img src={getTeamLogo(liveMatch.team_away)!} alt={liveMatch.team_away} className="w-9 h-9 sm:w-12 sm:h-12 object-contain" />
                    )}
                    <p className="text-sm sm:text-lg font-bold text-left">{liveMatch.team_away}</p>
                  </div>
                </div>
                <div className="text-center text-xs sm:text-sm text-hockey-text-secondary mb-3 sm:mb-4">
                  {parseMatchDate(liveMatch.datetime_utc).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
                </div>
                <Link
                  href={`/match/${liveMatch.id}`}
                  className="block w-full btn-red py-2.5 sm:py-3 rounded-xl text-xs sm:text-sm font-bold text-center"
                >
                  <span className="relative z-10">Смотреть</span>
                </Link>
              </div>
            </div>
          ) : nextKhl ? (
            <div className="animate-fade-in" style={{ animationDelay: "0.2s" }}>
              <div className="glass rounded-2xl p-4 sm:p-6 max-w-md mx-auto lg:ml-auto">
                <div className="flex items-center gap-2 mb-3 sm:mb-4">
                  <img src="/KHL.svg" alt="КХЛ" className="h-4 w-auto" />
                  <span className="text-[10px] sm:text-xs font-bold text-hockey-text-muted tracking-wider uppercase">Ближайший матч</span>
                </div>
                <div className="flex items-center justify-between gap-2 sm:gap-4 mb-3 sm:mb-4">
                  <div className="flex-1 flex items-center justify-end gap-2 sm:gap-3">
                    <p className="text-sm sm:text-lg font-bold text-right">{nextKhl.home}</p>
                    {getTeamLogo(nextKhl.home) && (
                      <img src={getTeamLogo(nextKhl.home)!} alt={nextKhl.home} className="w-9 h-9 sm:w-12 sm:h-12 object-contain" />
                    )}
                  </div>
                  <span className="text-[10px] sm:text-xs font-black text-hockey-text-muted">VS</span>
                  <div className="flex-1 flex items-center gap-2 sm:gap-3">
                    {getTeamLogo(nextKhl.away) && (
                      <img src={getTeamLogo(nextKhl.away)!} alt={nextKhl.away} className="w-9 h-9 sm:w-12 sm:h-12 object-contain" />
                    )}
                    <p className="text-sm sm:text-lg font-bold text-left">{nextKhl.away}</p>
                  </div>
                </div>
                <div className="text-center text-xs sm:text-sm text-hockey-text-secondary mb-3 sm:mb-4">
                  {nextKhl.time} МСК &middot; {new Date(nextKhl.date + "T00:00:00").toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}
                </div>
                <Link
                  href="/schedule"
                  className="block w-full btn-red py-2.5 sm:py-3 rounded-xl text-xs sm:text-sm font-bold text-center"
                >
                  <span className="relative z-10">Календарь</span>
                </Link>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function HeroSkeleton() {
  return (
    <section className="relative h-[85vh] min-h-[600px] flex items-center arena-bg">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 w-full">
        <div className="animate-pulse">
          <div className="h-6 bg-hockey-card rounded w-32 mb-6" />
          <div className="h-16 bg-hockey-card rounded w-96 mb-4" />
          <div className="h-16 bg-hockey-card rounded w-80 mb-4" />
          <div className="h-16 bg-hockey-card rounded w-64 mb-8" />
          <div className="h-12 bg-hockey-card rounded w-48" />
        </div>
      </div>
    </section>
  );
}

export default async function HomePage() {
  const matches = await getTodayMatches();

  return (
    <>
      <MatchNotifications />
      <Suspense fallback={<HeroSkeleton />}>
        <HeroSection />
      </Suspense>
      <LiveSectionClient initialMatches={matches} />
    </>
  );
}
