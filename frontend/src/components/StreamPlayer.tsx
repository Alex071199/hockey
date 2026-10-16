"use client";
import React from "react";
import HlsVideo from "@/components/HlsVideo";
import { isDirectHls } from "@/lib/sportplustv";
import useScreenAwake from "@/lib/useScreenAwake";

interface StreamPlayerProps {
  url: string;
  title: string;
}

function PiPButton({ iframeRef }: { iframeRef: React.RefObject<HTMLIFrameElement | null> }) {
  const [inPiP, setInPiP] = React.useState(false);
  const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);

  React.useEffect(() => {
    const handler = () => setInPiP(false);
    document.addEventListener("leavepictureinpicture", handler);
    return () => document.removeEventListener("leavepictureinpicture", handler);
  }, []);

  const toggle = async () => {
    try {
      const el = iframeRef.current;
      if (!el) return;
      if (document.pictureInPictureElement === el) {
        await document.exitPictureInPicture();
      } else {
        await (el as any).requestPictureInPicture();
        setInPiP(true);
      }
    } catch {}
  };

  if (isSafari) return null;

  return (
    <button
      onClick={toggle}
      className="absolute bottom-3 right-3 z-10 w-9 h-9 rounded-lg bg-black/60 text-white text-sm flex items-center justify-center hover:bg-hockey-accent/80 transition-colors border border-white/10"
      title="Картинка в картинке"
    >
      {inPiP ? "✕" : "⧍"}
    </button>
  );
}

/** Twitch принимает только parent=домен страницы, в которой встроен плеер,
 *  поэтому подставляем свой хост вместо доменов 1win. */
function withEmbedParent(url: string): string {
  if (!url.includes("player.twitch.tv")) return url;
  try {
    const u = new URL(url);
    u.searchParams.delete("parent");
    if (typeof window !== "undefined" && window.location.hostname) {
      u.searchParams.append("parent", window.location.hostname);
    }
    return u.toString();
  } catch {
    return url;
  }
}

function PlayerBody({ url, title }: StreamPlayerProps) {
  // Player fills the viewport height so no scrolling is needed to watch
  const playerBoxClass = "w-full h-[60svh] sm:h-[75svh] lg:h-[calc(100svh-100px)] min-h-[280px] sm:min-h-[420px]";

  // Хуки должны вызываться безусловно: раньше ref объявлялся внутри веток,
  // и переключение PRIME (ранний return) → iframe роняло React (global-error).
  const iframeRef = React.useRef<HTMLIFrameElement>(null);

  // Трансляция 1win: наш бэкенд отдаёт свежий master-плейлист с CORS,
  // играем hls.js напрямую; при ошибке подписи — автоматический перезапуск.
  if (url.includes("/api/broadcast/")) {
    return <HlsVideo url={url} title={title} retry={5} />;
  }

  const isDirectEmbed =
    url.includes("rutube.ru") ||
    url.includes("youtube.com") ||
    url.includes("vk.com") ||
    url.includes("ok.ru") ||
    url.includes(".m3u8") ||
    url.includes("vkvideo.ru") ||
    url.includes("player.twitch.tv");

  const needsProxy =
    url.includes("sportplus.watch") ||
    url.includes("web2.onsport365.live") ||
    url.includes("sportplustv.live") ||
    url.includes("pppdata.com") ||
    url.includes("sportvideodata.com") ||
    url.includes(".m3u8") ||
    url.includes("vitalsport1.ru") ||
    url.includes("milanolive.top") ||
    url.includes("playyy.php") ||
    url.includes("apl431.me") ||
    url.includes("apl430.me") ||
    url.includes("apl502.me") ||
    url.includes("peerflow") ||
    url.includes("buzznews4u.com") ||
    url.includes("livep2p.top") ||
    url.includes("onlinestreams.ru") ||
    url.includes("playfa.st") ||
    url.includes("shd247.world") ||
    url.includes("dynbetray.net") ||
    url.includes("varline.store") ||
    url.includes("wideiptv.top") ||
    url.includes("vdocity.com") ||
    url.includes("embedded.slevel.ru") ||
    url.includes("videocdn") ||
    url.includes("red.sport") ||
    url.includes("onhockey.tv") ||
    url.includes("livetv903.me") ||
    url.includes("livetv.sx") ||
    url.includes("/cdnlivetv");

  // Источники этого типа могут блокироваться провайдером (SNI/DNS) — предупреждаем,
  // вместо молчаливого чёрного плеера.
  const mayBeBlockedByProvider = /livetv\.sx|livetv903\.me|onhockey\.tv|youtube\.com/.test(url);

  const isAcestream = url.startsWith("acestream://");

  // Эти HLS-источники гео-заблокированы для нашего сервера (Railway, US),
  // но доступны пользователю — играем напрямую в браузере, минуя прокси.
  const directHls = url.includes(".m3u8") && isDirectHls(url);

  if (isAcestream) {
    return (
      <div className="relative rounded-xl overflow-hidden bg-black border border-hockey-border">
        <div className="aspect-video w-full flex flex-col items-center justify-center gap-3 sm:gap-4 p-4 sm:p-8 text-center">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-hockey-accent sm:w-16 sm:h-16">
            <polygon points="5 3 19 12 5 21 5 3" />
          </svg>
          <p className="text-hockey-text-secondary text-xs sm:text-sm max-w-md">
            AceStream трансляция — требуется приложение Ace Stream
          </p>
          <a
            href={url}
            className="inline-flex items-center gap-2 px-4 sm:px-6 py-2.5 sm:py-3 rounded-lg bg-hockey-accent text-white font-bold text-xs sm:text-sm hover:bg-hockey-accent/90 transition-all duration-200"
          >
            Открыть в Ace Stream
          </a>
        </div>
      </div>
    );
  }

  if (directHls) {
    return <HlsVideo url={url} title={title} />;
  }

  if (needsProxy) {
    const proxyUrl = `${process.env.NEXT_PUBLIC_API_URL}/api/proxy/stream?url=${encodeURIComponent(url)}`;
    return (
      <div className="relative rounded-xl overflow-hidden bg-black border border-hockey-border">
        <div className={playerBoxClass}>
          <iframe ref={iframeRef} src={proxyUrl} title={title} className="w-full h-full" allowFullScreen allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" />
          <PiPButton iframeRef={iframeRef} />
        </div>
        <div className="absolute top-0 left-0 right-0 h-16 bg-gradient-to-b from-black/80 via-black/40 to-transparent pointer-events-none" />
        <div className="px-3 py-2 text-[10px] sm:text-[11px] text-hockey-text-secondary bg-black/60 border-t border-hockey-border/50">
          Не загружается трансляция? Смени источник вверху или используй VPN
        </div>
      </div>
    );
  }

  if (!isDirectEmbed) {
    return (
      <div className="relative rounded-xl overflow-hidden bg-black border border-hockey-border">
        <div className="aspect-video w-full flex flex-col items-center justify-center gap-3 sm:gap-4 p-4 sm:p-8 text-center">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-hockey-accent sm:w-16 sm:h-16">
            <polygon points="5 3 19 12 5 21 5 3" />
          </svg>
          <p className="text-hockey-text-secondary text-xs sm:text-sm max-w-md">
            Трансляция доступна на сайте провайдера
          </p>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 sm:px-6 py-2.5 sm:py-3 rounded-lg bg-hockey-accent text-white font-bold text-xs sm:text-sm hover:bg-hockey-accent/90 transition-all duration-200"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <polyline points="15 3 21 3 21 9" />
              <line x1="10" y1="14" x2="21" y2="3" />
            </svg>
            Открыть трансляцию
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="relative rounded-xl overflow-hidden bg-black border border-hockey-border">
      <div className={playerBoxClass}>
        <iframe ref={iframeRef} src={withEmbedParent(url)} title={title} className="w-full h-full" allowFullScreen allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" />
        <PiPButton iframeRef={iframeRef} />
      </div>
      <div className="absolute top-0 left-0 right-0 h-16 bg-gradient-to-b from-black/80 via-black/40 to-transparent pointer-events-none" />
      {mayBeBlockedByProvider && (
        <div className="px-3 py-2 text-[10px] sm:text-[11px] text-hockey-text-secondary bg-black/60 border-t border-hockey-border/50">
          Не загружается трансляция? Смени источник вверху или используй VPN
        </div>
      )}
    </div>
  );
}

export default function StreamPlayer(props: StreamPlayerProps) {
  // Экран не засыпает, пока виден плеер: Wake Lock (iOS 16.4+) + фоновое видео.
  // Работает без UI (кнопка ручного включения убрана по просьбе).
  useScreenAwake(true);

  return <PlayerBody {...props} />;
}
