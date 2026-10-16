"use client";
import React from "react";

type Sentinel = {
  release: () => Promise<void>;
  addEventListener?: (type: "release", cb: () => void) => void;
};
type WakeLockNavigator = Navigator & {
  wakeLock?: { request: (type: "screen") => Promise<Sentinel> };
};

const RETRY_MS = 5000;

export interface ScreenAwake {
  /** navigator.wakeLock есть в этом браузере (iOS 16.4+ / Chrome 85+) */
  supported: boolean;
  /** wake lock реально удержан системой */
  locked: boolean;
  /** fallback-видео сейчас играет */
  videoPlaying: boolean;
  /** Включить удержание. ВАЖНО: вызывать из пользовательского жеста
   *  (тап/клик) — так wake lock и autoplay гарантированно стартуют
   *  даже там, где автозапуск браузер блокирует (Яндекс и т.п.). */
  enable: () => void;
  /** Выключить удержание (экономия батареи) */
  disable: () => void;
}

/**
 * Держит экран включённым, пока active === true (пока виден плеер).
 *
 * Два независимых механизма:
 * 1. Wake Lock API ("screen") — основной. Перезапрашивается каждые 5 с,
 *    сразу после молчаливого release от системы и по тапу.
 * 2. Невидимое зацикленное видео — fallback: воспроизведение видео не даёт
 *    экрану погаснуть ни на iOS (в т.ч. PWA/ярлык), ни на Android.
 *
 * Возвращает статус + ручные enable()/disable(): ручное включение внутри
 * жеста — единственный надёжный способ там, где браузер блокирует
 * автозапуск (см. кнопку «Экран не спит» в плеере).
 */
export default function useScreenAwake(active: boolean): ScreenAwake {
  const lockRef = React.useRef<Sentinel | null>(null);
  const videoRef = React.useRef<HTMLVideoElement | null>(null);
  const actionsRef = React.useRef<{ enable: () => void; disable: () => void }>({
    enable: () => {},
    disable: () => {},
  });

  const [supported, setSupported] = React.useState(false);
  const [locked, setLocked] = React.useState(false);
  const [videoPlaying, setVideoPlaying] = React.useState(false);

  React.useEffect(() => {
    if (!active) return;
    const nav = navigator as WakeLockNavigator;
    setSupported(!!nav.wakeLock);
    let disposed = false;
    let requeueTimer: ReturnType<typeof setTimeout> | null = null;
    let disabledByUser = false;

    const requestLock = async () => {
      if (disposed || disabledByUser || !nav.wakeLock || lockRef.current) return;
      if (document.visibilityState !== "visible") return;
      try {
        const lock = await nav.wakeLock.request("screen");
        if (disposed) {
          lock.release().catch(() => {});
          return;
        }
        lockRef.current = lock;
        setLocked(true);
        lock.addEventListener?.("release", () => {
          lockRef.current = null;
          setLocked(false);
          // Система может отнять блокировку молча (iOS-баг) — перезапрашиваем сразу
          if (disposed || disabledByUser || requeueTimer) return;
          requeueTimer = setTimeout(() => {
            requeueTimer = null;
            void requestLock();
          }, 500);
        });
      } catch {
        // отклонено (энергосбережение / старый iOS) — повторим по таймеру/жесту
      }
    };

    const ensureVideo = () => {
      if (disposed) return;
      let v = videoRef.current;
      if (!v) {
        v = document.createElement("video");
        v.src = "/awake-loop.mp4";
        v.muted = true;
        v.defaultMuted = true;
        v.loop = true;
        v.autoplay = true;
        v.playsInline = true;
        v.preload = "auto";
        v.setAttribute("playsinline", "");
        v.setAttribute("webkit-playsinline", "");
        v.setAttribute("muted", "");
        v.setAttribute("aria-hidden", "true");
        v.tabIndex = -1;
        v.style.cssText =
          "position:fixed;bottom:1px;right:1px;width:1px;height:1px;" +
          "opacity:0.01;pointer-events:none;z-index:2147483646;";
        const sync = () => setVideoPlaying(!v!.paused);
        // если система/браузер поставил видео на паузу — возвращаем воспроизведение
        v.addEventListener("pause", () => {
          sync();
          if (disposed || disabledByUser || document.visibilityState !== "visible") return;
          setTimeout(() => {
            if (!disposed && !disabledByUser && v && v.paused) {
              v.play().catch(() => {});
            }
          }, 200);
        });
        v.addEventListener("playing", sync);
        v.addEventListener("ended", sync);
        v.addEventListener("waiting", () => {
          if (disposed || disabledByUser) return;
          setTimeout(() => {
            if (!disposed && !disabledByUser && v && v.paused) v.play().catch(() => {});
          }, 500);
        });
        v.addEventListener("error", () => {
          if (disposed || disabledByUser) return;
          setTimeout(() => {
            if (disposed || disabledByUser) return;
            try {
              v!.load();
              v!.play().catch(() => {});
            } catch {}
          }, 1000);
        });
        document.body.appendChild(v);
        videoRef.current = v;
      }
      v.play().catch(() => {
        // автоплей заблокирован до первого жеста — переиграем из enable()
      });
    };

    const ensurePlaying = () => {
      if (disabledByUser) return;
      const v = videoRef.current;
      if (v && v.paused) v.play().catch(() => {});
    };

    const releaseLock = () => {
      lockRef.current?.release().catch(() => {});
      lockRef.current = null;
      setLocked(false);
    };

    const enable = () => {
      disabledByUser = false;
      // вызывается из жеста: и lock, и autoplay тут гарантированы
      void requestLock();
      ensureVideo();
      const v = videoRef.current;
      if (v) {
        v.muted = true;
        v.play().catch(() => {});
      }
    };

    const disable = () => {
      disabledByUser = true;
      releaseLock();
      videoRef.current?.pause();
    };

    actionsRef.current = { enable, disable };

    const onVisible = () => {
      if (document.visibilityState === "visible") {
        if (!disabledByUser) void requestLock();
        ensurePlaying();
      }
    };
    const onInteract = () => {
      if (disabledByUser) return;
      ensurePlaying();
      void requestLock();
    };

    if (!disabledByUser) void requestLock();
    ensureVideo();
    const retryTimer = setInterval(() => {
      if (!lockRef.current && !disabledByUser) void requestLock();
      ensurePlaying();
    }, RETRY_MS);

    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    window.addEventListener("pageshow", onVisible);
    document.addEventListener("pointerdown", onInteract);
    document.addEventListener("touchend", onInteract);

    return () => {
      disposed = true;
      clearInterval(retryTimer);
      if (requeueTimer) clearTimeout(requeueTimer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
      window.removeEventListener("pageshow", onVisible);
      document.removeEventListener("pointerdown", onInteract);
      document.removeEventListener("touchend", onInteract);
      releaseLock();
      videoRef.current?.pause();
      videoRef.current?.remove();
      videoRef.current = null;
      setLocked(false);
      setVideoPlaying(false);
      actionsRef.current = { enable: () => {}, disable: () => {} };
    };
  }, [active]);

  return React.useMemo(
    () => ({
      supported,
      locked,
      videoPlaying,
      enable: () => actionsRef.current.enable(),
      disable: () => actionsRef.current.disable(),
    }),
    [supported, locked, videoPlaying]
  );
}
