"use client";

import { useEffect, useState } from "react";

interface Toast {
  id: number;
  message: string;
}

let toastListeners: ((toast: Toast) => void)[] = [];

export function showToast(message: string) {
  const toast: Toast = { id: Date.now(), message };
  toastListeners.forEach((fn) => fn(toast));
}

export default function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    function handleToast(toast: Toast) {
      setToasts((prev) => [...prev, toast]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== toast.id));
      }, 5000);
    }
    toastListeners.push(handleToast);
    return () => {
      toastListeners = toastListeners.filter((fn) => fn !== handleToast);
    };
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="bg-hockey-surface border border-hockey-accent/30 rounded-xl px-4 py-3 shadow-lg shadow-hockey-accent/10 animate-fade-in max-w-xs"
        >
          <p className="text-sm font-medium text-white">{toast.message}</p>
        </div>
      ))}
    </div>
  );
}
