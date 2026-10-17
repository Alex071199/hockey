import TvPayForm from "./TvPayForm";

export default async function TvPayPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const sp = await searchParams;
  const chatId = typeof sp.chat_id === "string" ? sp.chat_id : "";
  const done = sp.done === "1" || sp.done === "true";

  if (done) {
    return (
      <div className="min-h-screen pt-24 pb-16 px-4">
        <div className="max-w-xl mx-auto text-center">
          <div className="text-5xl mb-6">✅</div>
          <h1 className="text-2xl sm:text-3xl font-black tracking-tight uppercase mb-4">
            Оплата получена
          </h1>
          <p className="text-hockey-text-secondary text-sm sm:text-base mb-4">
            Код активации для ТВ придёт в бот в течение минуты.
          </p>
          <p className="text-hockey-text-secondary text-sm sm:text-base">
            Откройте Telegram и введите код в приложении на телевизоре.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pt-24 pb-16 px-4">
      <div className="max-w-xl mx-auto text-center">
        <h1 className="text-2xl sm:text-3xl font-black tracking-tight uppercase mb-4">
          Активация ТВ
        </h1>
        <p className="text-hockey-text-secondary text-sm sm:text-base mb-8">
          Для работы приложения на телевизоре нужна активация — донат от 50 ₽ через ЮMoney.
          После оплаты бот пришлёт одноразовый 6-значный код.
        </p>
        {chatId ? (
          <TvPayForm chatId={chatId} />
        ) : (
          <p className="text-red-500 text-sm">Откройте ссылку из бота — она содержит идентификатор чата.</p>
        )}
      </div>
    </div>
  );
}
