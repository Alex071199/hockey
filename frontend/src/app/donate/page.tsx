import Link from "next/link";

export default function DonatePage() {
  return (
    <div className="min-h-screen pt-24 pb-16 px-4">
      <div className="max-w-xl mx-auto text-center">
        <h1 className="text-2xl sm:text-3xl font-black tracking-tight uppercase mb-4">
          Поддержать проект
        </h1>
        <p className="text-hockey-text-secondary text-sm sm:text-base mb-8">
          Если вам нравится HOCKEY LIVE и вы хотите помочь развитию проекта — вы можете сделать пожертвование. Каждый рубль помогает поддерживать серверы и улучшать сервис.
        </p>

        <a
          href="https://pay.cloudtips.ru/p/00cb8ffe"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-3 btn-red px-8 py-4 rounded-xl text-base sm:text-lg font-bold transition-all duration-200 hover:scale-105"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
          </svg>
          <span>Сделать пожертвование</span>
        </a>

        <div className="mt-12 pt-8 border-t border-hockey-border">
          <Link
            href="/"
            className="text-hockey-text-secondary hover:text-white text-sm transition-colors"
          >
            ← Вернуться на главную
          </Link>
        </div>
      </div>
    </div>
  );
}
