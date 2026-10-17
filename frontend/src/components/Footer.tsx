"use client";

import Link from "next/link";
import { useState } from "react";

export default function Footer() {
  const [showEmail, setShowEmail] = useState(false);

  return (
    <footer className="border-t border-hockey-border bg-hockey-surface">
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-12">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6 sm:gap-8 mb-8 sm:mb-10">
          <div>
            <div className="flex items-center gap-2 sm:gap-3 mb-3 sm:mb-4">
              <img src="/mainlogo.png" alt="HOCKEY LIVE" className="h-7 w-7 sm:h-8 sm:w-8 rounded-lg object-cover" />
              <span className="text-base sm:text-lg font-bold tracking-wider">
                HOCKEY<span className="text-hockey-accent"> LIVE</span>
              </span>
            </div>
            <p className="text-xs sm:text-sm text-hockey-text-secondary leading-relaxed">
              Стриминговая платформа для просмотра хоккейных матчей КХЛ, ВХЛ и МХЛ в прямом эфире.
            </p>
          </div>

          <div>
            <h3 className="text-xs sm:text-sm font-bold tracking-wider uppercase text-hockey-text-secondary mb-3 sm:mb-4">Навигация</h3>
            <ul className="space-y-2">
              <li><Link href="/" className="text-xs sm:text-sm text-hockey-text-muted hover:text-white transition-colors">Матчи</Link></li>
              <li><Link href="/schedule" className="text-xs sm:text-sm text-hockey-text-muted hover:text-white transition-colors">Календарь</Link></li>
              <li><Link href="/donate" className="text-xs sm:text-sm text-hockey-text-muted hover:text-white transition-colors">Поддержать</Link></li>
              <li>
                <button
                  onClick={() => setShowEmail(!showEmail)}
                  className="text-xs sm:text-sm text-hockey-text-muted hover:text-white transition-colors text-left"
                >
                  Реклама
                </button>
              </li>
              <li>
                <button
                  onClick={() => setShowEmail(!showEmail)}
                  className="text-xs sm:text-sm text-hockey-text-muted hover:text-white transition-colors text-left"
                >
                  Предложить идею
                </button>
              </li>
            </ul>
            {showEmail && (
              <div className="mt-3 p-3 rounded-lg bg-hockey-card border border-hockey-border text-xs sm:text-sm text-hockey-text-secondary">
                Все заявки принимаем на почту{" "}
                <a href="mailto:hockeylivesite@yahoo.com" className="text-hockey-accent hover:text-hockey-accent-hover transition-colors">
                  hockeylivesite@yahoo.com
                </a>
              </div>
            )}
          </div>

          <div>
            <h3 className="text-xs sm:text-sm font-bold tracking-wider uppercase text-hockey-text-secondary mb-3 sm:mb-4">Правовая информация</h3>
            <ul className="space-y-2">
              <li><Link href="/terms" className="text-xs sm:text-sm text-hockey-text-muted hover:text-white transition-colors">Условия использования</Link></li>
              <li><span className="text-xs sm:text-sm text-hockey-text-muted">18+</span></li>
              <li><span className="text-xs sm:text-sm text-hockey-text-muted">hockeylivesite@yahoo.com</span></li>
            </ul>
          </div>
        </div>

        <div className="border-t border-hockey-border pt-6 sm:pt-8 space-y-3 sm:space-y-4">
          <p className="text-[10px] sm:text-xs text-hockey-text-muted leading-relaxed">
            <strong>Уведомление о нарушении авторских прав:</strong> наш сервис — это поставщик технических услуг,
            который выступает в качестве поисковой системы для спортивных трансляций. Мы не размещаем и не загружаем
            мультимедийные файлы. Весь контент предоставляется сторонними организациями. Если вы считаете, что на ваш
            контент, защищённый авторским правом, ссылаются, пожалуйста, обратитесь к сторонним поставщикам услуг
            с просьбой удалить его.
          </p>
          <p className="text-[10px] sm:text-xs text-hockey-text-muted leading-relaxed">
            Все логотипы лиг <a href="https://www.khl.ru/" target="_blank" rel="noopener noreferrer" className="text-hockey-accent hover:text-hockey-accent-hover transition-colors">КХЛ</a>, <a href="https://mhl.khl.ru/" target="_blank" rel="noopener noreferrer" className="text-hockey-accent hover:text-hockey-accent-hover transition-colors">МХЛ</a> и <a href="https://www.vhlru.ru/" target="_blank" rel="noopener noreferrer" className="text-hockey-accent hover:text-hockey-accent-hover transition-colors">ВХЛ</a>, а также логотипы команд используются из сторонних сервисов и являются собственностью соответствующих организаций.
          </p>
          <p className="text-[10px] sm:text-xs text-hockey-text-muted leading-relaxed">
            Используя данный сервис, вы подтверждаете, что вам исполнилось 18 лет, и вы принимаете <Link href="/terms" className="text-hockey-accent hover:text-hockey-accent-hover transition-colors">условия использования</Link>.
          </p>
          <div className="flex items-center justify-between pt-3 sm:pt-4">
            <p className="text-[10px] sm:text-xs text-hockey-text-muted">
              &copy; 2026 HOCKEY LIVE
            </p>
            <div className="flex items-center gap-3">
              <a
                href="https://vk.ru/club240705499"
                target="_blank"
                rel="noopener noreferrer"
                className="w-8 h-8 rounded-lg bg-hockey-card border border-hockey-border flex items-center justify-center hover:border-hockey-accent/40 hover:bg-hockey-accent/10 transition-all duration-200"
              >
                <img src="/vk-mono.svg" alt="VK" className="w-4 h-4 opacity-60 group-hover:opacity-100" />
              </a>
              <a
                href="https://t.me/hockey_live27"
                target="_blank"
                rel="noopener noreferrer"
                className="w-8 h-8 rounded-lg bg-hockey-card border border-hockey-border flex items-center justify-center hover:border-hockey-accent/40 hover:bg-hockey-accent/10 transition-all duration-200"
              >
                <img src="/telegram-mono.svg" alt="Telegram" className="w-4 h-4 opacity-60 group-hover:opacity-100" />
              </a>
              <Link
                href="/download"
                title="Скачать приложение"
                className="w-8 h-8 rounded-lg bg-hockey-card border border-hockey-border flex items-center justify-center hover:border-hockey-accent/40 hover:bg-hockey-accent/10 transition-all duration-200"
              >
                <img src="/android.svg" alt="Android" className="w-4 h-4 opacity-60 group-hover:opacity-100" />
              </Link>
              <span className="text-[10px] sm:text-xs text-hockey-text-muted">
                18+ | 4+
              </span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
