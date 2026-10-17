"use client";

import { useEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

type PayForm = {
  form_action: string;
  fields: Record<string, string>;
  sum: number;
};

export default function TvPayForm({ chatId }: { chatId: string }) {
  const formRef = useRef<HTMLFormElement>(null);
  const [pay, setPay] = useState<PayForm | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(`${API_URL}/api/tv/request`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ chat_id: chatId }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data: PayForm = await r.json();
        if (!cancelled) setPay(data);
      } catch (e) {
        if (!cancelled) setError(`Не удалось создать оплату: ${(e as Error).message}`);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chatId]);

  useEffect(() => {
    if (pay && formRef.current && !submitting) {
      setSubmitting(true);
      formRef.current.submit();
    }
  }, [pay, submitting]);

  if (error) {
    return <p className="text-red-500 text-sm">{error}</p>;
  }

  if (!pay) {
    return <p className="text-hockey-text-secondary text-sm">Создаю счёт на оплату…</p>;
  }

  return (
    <div>
      <p className="text-hockey-text-secondary text-sm mb-4">
        Сейчас откроется форма оплаты ЮMoney на сумму {pay.sum} ₽.
      </p>
      <button
        type="button"
        className="btn-red px-8 py-4 rounded-xl text-base font-bold transition-all duration-200 hover:scale-105"
        onClick={() => formRef.current?.submit()}
      >
        Перейти к оплате {pay.sum} ₽
      </button>
      <form ref={formRef} action={pay.form_action} method="POST" className="hidden">
        {Object.entries(pay.fields).map(([name, value]) => (
          <input key={name} type="hidden" name={name} value={String(value)} />
        ))}
        <input type="submit" value="" />
      </form>
    </div>
  );
}
