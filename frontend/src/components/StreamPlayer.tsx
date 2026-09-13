"use client";

interface StreamPlayerProps {
  url: string;
  title: string;
}

export default function StreamPlayer({ url, title }: StreamPlayerProps) {
  // Player fills the viewport height so no scrolling is needed to watch
  const playerBoxClass = "w-full h-[calc(100svh-100px)] min-h-[420px]";

  const isDirectEmbed =
    url.includes("rutube.ru") ||
    url.includes("youtube.com") ||
    url.includes("vk.com") ||
    url.includes("ok.ru") ||
    url.includes(".m3u8") ||
    url.includes("vkvideo.ru");

  const needsProxy =
    url.includes("sportplus.watch") ||
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

  if (isAcestream) {
    return (
      <div className="relative rounded-xl overflow-hidden bg-black border border-hockey-border">
        <div className="aspect-video w-full flex flex-col items-center justify-center gap-4 p-8 text-center">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-hockey-accent">
            <polygon points="5 3 19 12 5 21 5 3" />
          </svg>
          <p className="text-hockey-text-secondary text-sm max-w-md">
            AceStream трансляция — требуется приложение Ace Stream
          </p>
          <a
            href={url}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-hockey-accent text-white font-bold text-sm hover:bg-hockey-accent/90 transition-all duration-200"
          >
            Открыть в Ace Stream
          </a>
        </div>
      </div>
    );
  }

  if (needsProxy) {
    const proxyUrl = `${process.env.NEXT_PUBLIC_API_URL}/api/proxy/stream?url=${encodeURIComponent(url)}`;
    return (
      <div className="relative rounded-xl overflow-hidden bg-black border border-hockey-border">
        <div className={playerBoxClass}>
          <iframe
            src={proxyUrl}
            title={title}
            className="w-full h-full"
            allowFullScreen
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          />
        </div>
        <div className="absolute top-0 left-0 right-0 h-16 bg-gradient-to-b from-black/80 via-black/40 to-transparent pointer-events-none" />
        <div className="px-3 py-2 flex items-center justify-between gap-2 text-[11px] text-hockey-text-secondary bg-black/60 border-t border-hockey-border/50">
          <span>
            Не запускается? Источник может быть заблокирован вашим провайдером (Livetv/OnHockey часто режут по SNI). На большинстве хостингов (Vercel и др.) прокси-резолвер сам достаёт источник.
          </span>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-hockey-accent text-white font-semibold text-xs hover:bg-hockey-accent/90 transition-colors"
          >
            Открыть источник
          </a>
        </div>
      </div>
    );
  }

  if (!isDirectEmbed) {
    return (
      <div className="relative rounded-xl overflow-hidden bg-black border border-hockey-border">
        <div className="aspect-video w-full flex flex-col items-center justify-center gap-4 p-8 text-center">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-hockey-accent">
            <polygon points="5 3 19 12 5 21 5 3" />
          </svg>
          <p className="text-hockey-text-secondary text-sm max-w-md">
            Трансляция доступна на сайте провайдера
          </p>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-hockey-accent text-white font-bold text-sm hover:bg-hockey-accent/90 transition-all duration-200"
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
        <iframe
          src={url}
          title={title}
          className="w-full h-full"
          allowFullScreen
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        />
      </div>
      <div className="absolute top-0 left-0 right-0 h-16 bg-gradient-to-b from-black/80 via-black/40 to-transparent pointer-events-none" />
      {mayBeBlockedByProvider && (
        <div className="px-3 py-2 text-[10px] sm:text-[11px] text-hockey-text-secondary bg-black/60 border-t border-hockey-border/50">
          Не запускается? Источник может быть заблокирован вашим провайдером — включите VPN и обновите страницу, либо выберите другой источник выше.
        </div>
      )}
    </div>
  );
}
