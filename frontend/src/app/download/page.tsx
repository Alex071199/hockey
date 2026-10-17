"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const APK_URL =
  "https://github.com/Alex071199/hockey/releases/latest/download/HockeyLiveTV.apk";
const GITHUB_RELEASES = "https://github.com/Alex071199/hockey/releases";
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

const steps = [
  {
    title: "Установите APK",
    text: "Скачайте файл и разрешите установку из неизвестных источников (на ТВ: Настройки → Безопасность).",
  },
  {
    title: "Откройте Telegram",
    text: "Отсканируйте QR-код на экране активации или найдите бота вручную: @hockeylivenotificationbot.",
  },
  {
    title: "Нажмите «Подключить ТВ»",
    text: "Кнопка в меню бота откроет страницу активации.",
  },
];

const features = [
  { title: "КХЛ, ВХЛ, МХЛ и НХЛ", text: "Все трансляции в одном приложении" },
  { title: "Статистика и составы", text: "Голы, удаления и составы по командам" },
  { title: "Обновления в один клик", text: "Окно обновления появится в приложении" },
];

export default function DownloadPage() {
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/api/app/version`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.version) setVersion(d.version);
      })
      .catch(() => {});
  }, []);

  return (
    <div className="min-h-screen pt-24 pb-16 px-4">
      <div className="max-w-2xl mx-auto text-center">
        <h1 className="text-2xl sm:text-3xl font-black tracking-tight uppercase mb-4">
          Приложение Hockey Live
        </h1>
        <p className="text-hockey-text-secondary text-sm sm:text-base mb-8">
          Матчи КХЛ, ВХЛ, МХЛ и НХЛ на большом экране — с той же статистикой,
          что и на сайте. Для Android-смартфонов и Android TV.
        </p>

        <div className="bg-hockey-card border border-hockey-border rounded-2xl p-6 sm:p-8 mb-8">
          <img
            src="/android.svg"
            alt="Android"
            className="h-16 w-auto mx-auto mb-4"
          />
          <a
            href={APK_URL}
            className="inline-flex items-center gap-3 btn-red px-8 py-4 rounded-xl text-base sm:text-lg font-bold transition-all duration-200 hover:scale-105"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            <span>Скачать APK</span>
          </a>
          <p className="text-hockey-text-muted text-xs sm:text-sm mt-4">
            {version ? `Текущая версия: ${version} · ` : ""}
            ссылка всегда ведёт на последнюю версию
          </p>
          <a
            href={GITHUB_RELEASES}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block text-hockey-accent hover:text-hockey-accent-hover text-xs sm:text-sm mt-2 transition-colors"
          >
            Все версии на GitHub →
          </a>
        </div>

        <div className="text-left bg-hockey-card border border-hockey-border rounded-2xl p-6 sm:p-8 mb-8">
          <h2 className="text-sm font-bold tracking-wider uppercase text-hockey-text-secondary mb-5">
            Как установить и активировать
          </h2>
          <ol className="space-y-4">
            {steps.map((s, i) => (
              <li key={s.title} className="flex gap-4">
                <span className="shrink-0 w-7 h-7 rounded-full bg-hockey-accent/15 text-hockey-accent text-sm font-bold flex items-center justify-center">
                  {i + 1}
                </span>
                <div>
                  <p className="text-sm font-semibold text-white">{s.title}</p>
                  <p className="text-xs sm:text-sm text-hockey-text-secondary leading-relaxed">
                    {s.text}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-10">
          {features.map((f) => (
            <div
              key={f.title}
              className="bg-hockey-card border border-hockey-border rounded-xl p-4"
            >
              <p className="text-sm font-semibold text-white mb-1">{f.title}</p>
              <p className="text-xs text-hockey-text-secondary">{f.text}</p>
            </div>
          ))}
        </div>

        <Link
          href="/"
          className="text-hockey-text-secondary hover:text-white text-sm transition-colors"
        >
          ← Вернуться на главную
        </Link>
      </div>
    </div>
  );
}
