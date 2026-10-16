"use client";
import React from "react";

/**
 * Прямое HLS-воспроизведение в браузере (без серверного прокси).
 * Используется для источников, гео-заблокированных для нашего сервера,
 * но доступных пользователю (CORS на этих CDN открыт).
 *
 * retry — сколько раз перезапустить загрузку manifest'а после фатальной
 * ошибки (нужно для источников с подписанной, протухающей ссылкой).
 */
export default function HlsVideo({ url, title, retry = 0, compact = false }: { url: string; title: string; retry?: number; compact?: boolean }) {
  const videoRef = React.useRef<HTMLVideoElement>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [reload, setReload] = React.useState(0);
  const attemptsRef = React.useRef(0);
  const boxClass = compact
    ? "w-full aspect-video"
    : "w-full h-[60svh] sm:h-[75svh] lg:h-[calc(100svh-100px)] min-h-[280px] sm:min-h-[420px]";

  React.useEffect(() => {
    attemptsRef.current = 0;
    setError(null);
  }, [url]);

  React.useEffect(() => {
    let cancelled = false;
    let hls: any = null;
    const video = videoRef.current;
    if (!video) return;

    const play = async () => {
      try {
        const Hls = (await import("hls.js")).default;
        if (cancelled) return;

        if (Hls.isSupported()) {
          hls = new Hls({
            enableWorker: true,
            lowLatencyMode: false,
            // старт через наш прокси медленнее прямого CDN — даём себе
            // запас, чтобы первые секунды не заикались
            maxBufferLength: 60,
            maxMaxBufferLength: 120,
            liveSyncDurationCount: 5,
            startFragPrefetch: true,
          });
          hls.loadSource(url);
          hls.attachMedia(video);
          hls.on(Hls.Events.ERROR, (_: unknown, data: any) => {
            if (!data?.fatal || cancelled) return;
            if (attemptsRef.current < retry) {
              attemptsRef.current += 1;
              setTimeout(() => {
                if (!cancelled) setReload((r) => r + 1);
              }, 2500);
              return;
            }
            setError("Не удалось загрузить трансляцию");
            try {
              hls?.destroy();
            } catch {}
          });
        } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
          // Safari / iOS — нативная поддержка HLS
          video.src = url;
        } else {
          setError("Браузер не поддерживает HLS");
        }
        await video.play().catch(() => {});
      } catch {
        setError("Не удалось загрузить трансляцию");
      }
    };

    play();
    return () => {
      cancelled = true;
      try {
        hls?.destroy();
      } catch {}
      video.removeAttribute("src");
      video.load();
    };
  }, [url, reload, retry]);

  return (
    <div className="relative rounded-xl overflow-hidden bg-black border border-hockey-border">
      <div className={boxClass}>
        <video
          ref={videoRef}
          className="w-full h-full bg-black object-contain"
          controls
          playsInline
          autoPlay
          muted={false}
          title={title}
        />
      </div>
      {error ? (
        <div className="absolute inset-0 flex items-center justify-center bg-black/80">
          <p className="text-hockey-text-secondary text-xs sm:text-sm px-4 text-center">
            {error}. Попробуй сменить источник или включи VPN.
          </p>
        </div>
      ) : null}
      {!compact && (
        <div className="px-3 py-2 text-[10px] sm:text-[11px] text-hockey-text-secondary bg-black/60 border-t border-hockey-border/50">
          Не загружается трансляция? Смени источник вверху или используй VPN
        </div>
      )}
    </div>
  );
}
