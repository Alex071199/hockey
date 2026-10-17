import asyncio
import json
import logging
import re
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from urllib.parse import urlparse

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, Response

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/proxy", tags=["proxy"])

CURL = shutil.which("curl") or "curl"
_cache: dict[str, tuple[float, str]] = {}
CACHE_TTL = 300


def _urllib_get_sync(url: str, referer: str = "") -> str:
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win6; x64) AppleWebKit/537.36",
        })
        if referer:
            req.add_header("Referer", referer)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            if len(data) > 50:
                return data.decode("utf-8", errors="ignore")
    except Exception:
        pass
    return ""


def _curl_get_sync(url: str, retries: int = 2, referer: str = "") -> str:
    for attempt in range(retries):
        try:
            cmd = [
                CURL, "-s", "-k", "-L",
                "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win6; x64) AppleWebKit/537.36",
                "--connect-timeout", "10",
                "--max-time", "20",
            ]
            if referer:
                cmd += ["-H", f"Referer: {referer}"]
            cmd.append(url)
            r = subprocess.run(cmd, capture_output=True, timeout=25)
            if r.stdout and len(r.stdout) > 50:
                return r.stdout.decode("utf-8", errors="ignore")
        except Exception:
            pass
    return ""


def _fetch_sync(url: str, retries: int = 2, referer: str = "") -> str:
    result = _curl_get_sync(url, retries, referer)
    if result:
        return result
    return _urllib_get_sync(url, referer)


def _curl_get_bytes(url: str, retries: int = 2, referer: str = "") -> bytes:
    for attempt in range(retries):
        try:
            cmd = [
                CURL, "-s", "-k", "-L",
                "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win6; x64) AppleWebKit/537.36",
                "--connect-timeout", "10",
                "--max-time", "30",
            ]
            if referer:
                cmd += ["-H", f"Referer: {referer}"]
            cmd.append(url)
            r = subprocess.run(cmd, capture_output=True, timeout=35)
            if r.stdout:
                return r.stdout
        except Exception:
            pass
    return b""


async def _fetch_page(url: str, referer: str = "", no_cache: bool = False) -> str:
    cache_key = f"{url}|{referer}"
    if not no_cache:
        cached = _cache.get(cache_key)
        if cached and time.time() - cached[0] < CACHE_TTL:
            return cached[1]
    loop = asyncio.get_event_loop()
    html = await loop.run_in_executor(None, _fetch_sync, url, 2, referer)
    if html and not no_cache:
        _cache[cache_key] = (time.time(), html)
    return html


def _resolve_url(src: str, base_url: str) -> str:
    if src.startswith("//"):
        return "https:" + src
    elif src.startswith("/"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{src}"
    return src


def _extract_iframes(html: str) -> list[str]:
    results = []
    for m in re.finditer(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE):
        raw = m.group(1)
        cleaned = re.sub(r'[\s]+', '', raw).strip()
        if cleaned:
            results.append(cleaned)
    return results


def _hls_player_page(m3u8_url: str, proxy: bool = True) -> str:
    if proxy:
        proxy_base = settings.PUBLIC_API_URL.rstrip("/")
        play_url = f"{proxy_base}/api/proxy/hls-proxy?url={m3u8_url}"
    else:
        play_url = m3u8_url
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="referrer" content="no-referrer">
<script src="https://cdn.jsdelivr.net/npm/hls.js@1"></script>
<style>
  body {{ margin:0; padding:0; background:#000; overflow:hidden; }}
  video {{ width:100vw; height:100vh; object-fit:contain; display:block; }}
</style>
</head>
<body>
<video id="v" controls autoplay playsinline></video>
<script>
var video=document.getElementById('v');
var src='{play_url}';
if(Hls.isSupported()){{var hls=new Hls();hls.loadSource(src);hls.attachMedia(video);hls.on(Hls.Events.MANIFEST_PARSED,function(){{video.play()}});}}
else if(video.canPlayType('application/vnd.apple.mpegurl')){{video.src=src;video.play();}}
</script>
</body>
</html>"""


_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _media_player_page(src: str) -> str:
    """Плеер для резолвленных embed: m3u8 через hls-proxy (CORS), mp4 напрямую."""
    proxy_base = settings.PUBLIC_API_URL.rstrip("/")
    if ".m3u8" in src:
        play_url = f"{proxy_base}/api/proxy/hls-proxy?url={src}"
    else:
        play_url = src
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="referrer" content="no-referrer">
<script src="https://cdn.jsdelivr.net/npm/hls.js@1"></script>
<style>
  body {{ margin:0; padding:0; background:#000; overflow:hidden; }}
  video {{ width:100vw; height:100vh; object-fit:contain; display:block; }}
</style>
</head>
<body>
<video id="v" controls autoplay playsinline></video>
<script>
var video=document.getElementById('v');
var src='{play_url}';
if(src.indexOf('.m3u8')>=0){{
  if(Hls.isSupported()){{var hls=new Hls();hls.loadSource(src);hls.attachMedia(video);hls.on(Hls.Events.MANIFEST_PARSED,function(){{video.play()}});}}
  else if(video.canPlayType('application/vnd.apple.mpegurl')){{video.src=src;video.play();}}
}}else{{video.src=src;video.play();}}
</script>
</body>
</html>"""


def _post_json_sync(url: str, payload: dict) -> dict | None:
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": _BROWSER_UA,
                "Accept-Language": "ru-RU,ru;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception:
        return None


def _youtube_video_id(url: str) -> str:
    m = re.search(r"youtube\.com/embed/([\w-]{6,})", url)
    if not m:
        m = re.search(r"youtu\.be/([\w-]{6,})", url)
    return m.group(1) if m else ""


async def _resolve_youtube(url: str) -> str | None:
    """Embed YouTube → HLS-манифест (live) или mp4 (VOD) через Innertube API."""
    vid = _youtube_video_id(url)
    if not vid:
        return None
    cache_key = f"yt_embed|{vid}"
    cached = _cache.get(cache_key)
    if cached and time.time() - cached[0] < 300:
        return cached[1]

    # разные клиенты innertube: WEB иногда отдаёт UNPLAYABLE без cookies,
    # ANDROID/IOS/TVHTML5 — чаще отдают потоки напрямую
    clients = [
        ("WEB", "2.20260101.01.00", {}),
        ("ANDROID", "20.10.38", {"androidSdkVersion": 30}),
        ("IOS", "20.10.4", {"deviceModel": "iPhone14,3", "osName": "iPhone", "osVersion": "16.0"}),
        ("TVHTML5", "7.20251001.15.00", {}),
    ]

    def _call(client_name: str, version: str, extra: dict) -> dict | None:
        client = {"clientName": client_name, "clientVersion": version, "hl": "ru", "gl": "RU"}
        client.update(extra)
        return _post_json_sync(
            "https://www.youtube.com/youtubei/v1/player?prettyPrint=false",
            {
                "context": {"client": client},
                "videoId": vid,
                "contentCheckOk": True,
                "racyCheckOk": True,
                "playbackContext": {
                    "contentPlaybackContext": {"html5Preference": "HTML5_PREF_WANTS"}
                },
            },
        )

    loop = asyncio.get_event_loop()
    src: str | None = None
    for client_name, version, extra in clients:
        data = await loop.run_in_executor(None, _call, client_name, version, extra)
        if not data:
            logger.warning("youtube resolve %s: %s no response", vid, client_name)
            continue
        streaming = data.get("streamingData") or {}
        candidate = streaming.get("hlsManifestUrl")
        if not candidate:
            for fmt in reversed(streaming.get("formats") or []):
                if fmt.get("url"):
                    candidate = fmt["url"]
                    break
        status = (data.get("playabilityStatus") or {}).get("status")
        logger.warning(
            "youtube resolve %s via %s: status=%s got=%s",
            vid, client_name, status, bool(candidate),
        )
        if candidate:
            src = candidate
            break

    if not src:
        return None
    _cache[cache_key] = (time.time(), src)
    return src


def _rutube_video_id(url: str) -> str:
    m = re.search(r"rutube\.ru/play/embed/([\w-]+)", url)
    return m.group(1) if m else ""


async def _resolve_rutube(url: str) -> str | None:
    """Embed Rutube → HLS из play/options (VOD: video_balancer, live: live_streams)."""
    vid = _rutube_video_id(url)
    if not vid:
        return None
    cache_key = f"rt_embed|{vid}"
    cached = _cache.get(cache_key)
    if cached and time.time() - cached[0] < 300:
        return cached[1]

    loop = asyncio.get_event_loop()
    body = await loop.run_in_executor(
        None,
        _fetch_sync,
        f"https://rutube.ru/api/play/options/{vid}/",
        2,
        "https://rutube.ru/",
    )
    if not body:
        logger.warning("rutube resolve %s: empty response", vid)
        return None
    try:
        info = json.loads(body)
    except Exception:
        logger.warning("rutube resolve %s: bad json", vid)
        return None

    src: str | None = None
    vb = info.get("video_balancer")
    if isinstance(vb, dict):
        src = vb.get("m3u8") or vb.get("m3u8_m4s")
    elif isinstance(vb, str):
        src = vb
    if not src:
        options = info.get("video_balancer_options") or []
        for opt in options:
            if isinstance(opt, dict) and opt.get("src"):
                src = opt["src"]
                break
    if not src:
        # live-стримы: подписанный HLS на сутки
        for item in (info.get("live_streams") or {}).get("hls") or []:
            if item.get("url"):
                src = item["url"]
                break
    logger.warning(
        "rutube resolve %s: is_live=%s balancer=%s live_streams=%s got=%s",
        vid,
        info.get("stream_type") == "stream_push",
        bool(vb),
        bool(info.get("live_streams")),
        bool(src),
    )
    if not src:
        return None
    _cache[cache_key] = (time.time(), src)
    return src


def _direct_frame_page(player_url: str, referrer: str = "https://livetv.sx/") -> str:
    """Embed the third-party player page directly from the browser.

    The player issues its signed stream token to the IP that requested the
    player page, so the page MUST be loaded by the viewer's browser, not by
    our backend. Referrer is forced to livetv.sx (non-empty + canonical).
    """
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="referrer" content="{referrer}">
<style>
  html,body {{ margin:0; padding:0; background:#000; height:100%; overflow:hidden; }}
  iframe {{ border:0; width:100vw; height:100vh; position:fixed; top:0; left:0; }}
</style>
</head>
<body>
<iframe src="{player_url}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen" allowfullscreen></iframe>
</body>
</html>"""


def _wrap_player_page(html: str, source_url: str) -> str:
    """Wrap a player page to break iframe detection.
    Inject window.top override for vdocity (which checks self===top and refuses to load).
    Skip for cuttingfame/403 pages (they check window==window.top to BLOCK top-level)."""
    parsed = urlparse(source_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    html = re.sub(r'<base[^>]*>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'<meta\s+name=["\']referrer["\'][^>]*>', '', html, flags=re.IGNORECASE)

    is_vdocity = "vdocity" in source_url.lower()
    is_blocked = "Not allowed" in html or "403 Forbidden" in html

    if is_blocked:
        return html

    inject = '<meta name="referrer" content="no-referrer">\n'

    if is_vdocity:
        inject += (
            '<script>\n'
            '(function(){\n'
            '  try{\n'
            '    var desc=Object.getOwnPropertyDescriptor(window.__proto__,"top")||\n'
            '             Object.getOwnPropertyDescriptor(Window.prototype,"top");\n'
            '    if(desc&&desc.get){\n'
            '      Object.defineProperty(window,"top",{get:function(){return window;},configurable:true});\n'
            '    }else{window.top=window;}\n'
            '  }catch(e){try{window.top=window;}catch(e2){}}\n'
            '})();\n'
            '</script>\n'
        )

    html = html.replace("<head>", "<head>" + inject, 1)
    if "<base" not in html.lower():
        html = re.sub(r'<head>', f'<head>\n<base href="{origin}/">', html, count=1, flags=re.IGNORECASE)

    html = re.sub(r'src="/', f'src="{origin}/', html)
    html = re.sub(r"src='/", f"src='{origin}/", html)
    html = re.sub(r'href="/', f'href="{origin}/', html)
    html = re.sub(r"href='/", f"href='{origin}/", html)
    html = html.replace(f'src="{origin}//', 'src="https://')
    html = html.replace(f"src='{origin}//", "src='https://")
    html = html.replace(f'href="{origin}//', 'href="https://')
    html = html.replace(f"href='{origin}//", "href='https://")

    return html


def _failed_page() -> str:
    return """<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><style>
  body{margin:0;padding:0;background:#05070d;color:#cfd6e4;font-family:Segoe UI,Arial,sans-serif;
       display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center}
  .box{max-width:560px;padding:32px}
  h2{margin:0 0 10px;color:#ff4d4d;font-size:20px}
  p{font-size:14px;line-height:1.6;opacity:.85;margin:6px 0}
</style></head>
<body><div class="box">
  <h2>Трансляция не запускается</h2>
  <p>Не загружается трансляция? Смени источник вверху или используй VPN.</p>
</div></body></html>"""


async def _extract_m3u8_from_inner_player(player_url: str, referer: str, no_cache: bool = False) -> str | None:
    html = await _fetch_page(player_url, referer=referer, no_cache=no_cache)
    if not html:
        return None
    for pattern in [
        r"['\"]?(https?://[^'\"\s\\]+\.m3u8[^'\"\s\\]*)",
        r"['\"]?(//[^'\"\s\\]+\.m3u8[^'\"\s\\]*)",
        r"pl\.init\(\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]\s*\)",
        r"streamUrl:\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]",
        r"['\"]?(https?:\\/\\/[^'\"\s]+\.m3u8[^'\"\s]*)",
    ]:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            url = m.group(1).rstrip("'\";(),")
            url = url.replace("\\/", "/")
            url = re.sub(r'[\s]+', '', url)
            if url.startswith("//"):
                url = "https:" + url
            if url.startswith("http"):
                return url
    return None


def _is_ad_url(url: str) -> bool:
    skip = ["getbanner", "livetv904.me/player/links", "googleads", "doubleclick",
            "adskeeper", "ads.livetv", "plausible", "gtag", "histats"]
    return any(s in url.lower() for s in skip)


def _is_player_domain(url: str) -> bool:
    domains = ["hlsplayers", "azplay", "apl613", "apl605", "apl431", "apl430",
               "cuttingfame", "embedded.slevel", "peerflow", "livetv904.me/player",
               "vdocity.com", "vdocity"]
    return any(d in url.lower() for d in domains)


def _pick_player_iframe(html: str, base_url: str) -> str | None:
    """URL iframe с самим плеером во веб-плеере livetv (реклама отбрасывается)."""
    fallback = None
    keys = (".php", "/player", "embed", "sonic", "stream", ".html", "hls", "play")
    for src in _extract_iframes(html):
        full_src = _resolve_url(src, base_url)
        low = full_src.lower()
        if _is_ad_url(low) or "ltv_popup" in low:
            continue
        if any(k in low for k in keys):
            return full_src
        if fallback is None:
            fallback = full_src
    return fallback


async def _follow_iframes_deep(html: str, base_url: str, depth: int = 0):
    if depth > 5:
        return None

    inner_iframes = _extract_iframes(html)

    for iframe_src in inner_iframes:
        full_src = _resolve_url(iframe_src, base_url)
        if _is_ad_url(full_src):
            continue
        m3u8 = await _extract_m3u8_from_inner_player(full_src, referer="https://livetv.sx/", no_cache=True)
        if m3u8:
            return ("m3u8", m3u8)

    for iframe_src in inner_iframes:
        full_src = _resolve_url(iframe_src, base_url)
        if _is_ad_url(full_src):
            continue
        if "ltv_popup" in full_src:
            continue

        if _is_player_domain(full_src) or "php" in full_src.lower() or "player" in full_src.lower():
            inner_html = await _fetch_page(full_src, referer="https://livetv.sx/", no_cache=True)
            if inner_html:
                inner_base = str(urlparse(full_src).scheme + "://" + urlparse(full_src).netloc)
                deeper = await _follow_iframes_deep(inner_html, inner_base, depth + 1)
                if deeper:
                    return deeper
                if _is_player_domain(full_src):
                    return ("player_html", inner_html, full_src)

    return None


async def _resolve_livetv_player(webplayer_url: str) -> str | None:
    html = await _fetch_page(webplayer_url, referer="https://livetv.sx/", no_cache=True)
    if not html:
        return None

    parsed_lp = urlparse(webplayer_url)
    base_url = f"{parsed_lp.scheme}://{parsed_lp.netloc}"

    result = await _follow_iframes_deep(html, base_url)
    if result:
        if result[0] == "m3u8":
            return _hls_player_page(result[1], proxy=True)
        elif result[0] == "player_html":
            if "Not allowed" in result[1] or "403 Forbidden" in result[1]:
                pass
            elif "cuttingfame" in result[2].lower():
                return _direct_frame_page(result[2])
            else:
                return _wrap_player_page(result[1], result[2])

    # youtube-транспорт: веб-плеер livetv — это рекламная страница со
    # ссылками поверх плеера; оставляем только сам embed ролика
    m_yt = re.search(
        r'((?:https?:)?//(?:www\.)?youtube\.com/embed/[A-Za-z0-9_-]+(?:\?[^"\'\s]*)?)',
        html,
    )
    if m_yt:
        yt_src = m_yt.group(1).replace("&amp;", "&")
        if yt_src.startswith("//"):
            yt_src = "https:" + yt_src
        if "autoplay" not in yt_src:
            yt_src += ("&" if "?" in yt_src else "?") + "autoplay=1"
        # no-referrer → YouTube отдаёт Error 153 («Ошибка настройки
        # видеопроигрывателя»): embed обязан получать непустой referrer.
        return _direct_frame_page(yt_src, referrer="origin")

    player_iframe = _pick_player_iframe(html, base_url)
    if player_iframe:
        return _direct_frame_page(player_iframe, referrer="origin")

    # вычищаем попандер/оверлей и рекламные iframes веб-плеера
    html = re.sub(
        r'<script[^>]*src="[^"]*ltv_popup[^"]*"[^>]*>\s*</script>', "", html, flags=re.I
    )
    html = re.sub(r'<div id="localpp".*?</div>', "", html, flags=re.S | re.I)
    html = re.sub(
        r"document\.write\(\s*'<iframe allowTransparency.*?</iframe>'\);",
        "",
        html,
        flags=re.S | re.I,
    )
    html = re.sub(
        r'document\.write\("<iframe[^>]*player/links.*?</iframe>"\);', "", html, flags=re.S | re.I
    )
    html = re.sub(
        r'<iframe[^>]*src="[^"]*(?:getbanner|player/links)[^"]*"[^>]*>\s*</iframe>',
        "",
        html,
        flags=re.I,
    )

    if "<base" not in html.lower():
        html = html.replace("<head>", f'<head>\n<base href="{base_url}/">', 1)

    html = html.replace('src="/', f'src="{base_url}/')
    html = html.replace("src='/", f"src='{base_url}/")
    html = html.replace(f'src="{base_url}//', 'src="https://')
    html = html.replace(f"src='{base_url}//", "src='https://")
    html = html.replace(f'href="{base_url}//', 'href="https://')
    html = html.replace(f"href='{base_url}//", "href='https://")

    referrer_meta = '<meta name="referrer" content="no-referrer">\n'

    if "webplayer2.php" in webplayer_url:
        inject = (
            referrer_meta
            + '<style>\n'
            '  body { margin:0; padding:0; background:#000; overflow:hidden; }\n'
            '  iframe { width:100vw; height:100vh; border:none; position:fixed; top:0; left:0; }\n'
            '</style>\n'
        )
    else:
        inject = (
            referrer_meta
            + '<style>\n'
            '  body { background:#000 !important; }\n'
            '  body > * { display:none !important; }\n'
            '  iframe[src*="getbanner"] { display:none !important; }\n'
            '</style>\n'
            '<script>\n'
            'document.addEventListener("DOMContentLoaded",function(){\n'
            '  document.querySelectorAll("iframe").forEach(function(f){\n'
            '    if(!f.src||f.src.indexOf("getbanner")>=0){f.remove();return;}\n'
            '    f.style.cssText="width:100vw;height:100vh;border:none;position:fixed;top:0;left:0;z-index:999999;";\n'
            '  });\n'
            '  document.body.style.cssText="margin:0;padding:0;background:#000;overflow:hidden;";\n'
            '  var pb=document.getElementById("playerblock");\n'
            '  if(pb){pb.style.cssText="display:block!important;position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:999999;background:#000;";document.body.appendChild(pb);}\n'
            '  var kids=document.body.children;\n'
            '  for(var i=kids.length-1;i>=0;i--){if(kids[i]!==pb)kids[i].remove();}\n'
            '});\n'
            '</script>\n'
        )
    html = html.replace("<head>", "<head>" + inject, 1)

    return html


@router.get("/stream")
async def proxy_stream(url: str = Query(..., description="Stream page URL")):
    # embed YouTube/Rutube: системный WebView на TV-боксах их не проигрывает —
    # резолвим в чистый HLS/mp4-плеер (иначе чёрный экран на МХЛ/ВХЛ)
    if "youtube.com/embed/" in url or "youtu.be/" in url:
        src = await _resolve_youtube(url)
        if src:
            return HTMLResponse(content=_media_player_page(src), media_type="text/html; charset=utf-8")
        return HTMLResponse(_failed_page(), media_type="text/html; charset=utf-8", status_code=502)

    if "rutube.ru/play/embed/" in url:
        src = await _resolve_rutube(url)
        if src:
            return HTMLResponse(content=_media_player_page(src), media_type="text/html; charset=utf-8")
        return HTMLResponse(_failed_page(), media_type="text/html; charset=utf-8", status_code=502)

    is_livetv = "livetv903.me" in url or "livetv.sx" in url or "livetv904.me" in url
    is_onsport = "onsport365.live" in url or "sportplustv.live" in url
    is_m3u8 = url.endswith(".m3u8") or ".m3u8?" in url
    parsed = urlparse(url)

    if is_m3u8:
        return HTMLResponse(content=_hls_player_page(url, proxy=True), media_type="text/html; charset=utf-8")

    if is_livetv:
        resolved = await _resolve_livetv_player(url)
        if resolved:
            return HTMLResponse(content=resolved, media_type="text/html; charset=utf-8")
        return HTMLResponse(_failed_page(), media_type="text/html; charset=utf-8", status_code=502)

    html = await _fetch_page(url)
    if not html:
        return HTMLResponse(_failed_page(), media_type="text/html; charset=utf-8", status_code=502)

    if is_onsport:
        origin = f"{parsed.scheme}://{parsed.netloc}"
        inject = (
            '<meta name="referrer" content="no-referrer">\n'
            '<script>\n'
            '(function(){\n'
            '  try{\n'
            '    var desc=Object.getOwnPropertyDescriptor(window.__proto__,"top")||\n'
            '             Object.getOwnPropertyDescriptor(Window.prototype,"top");\n'
            '    if(desc&&desc.get){\n'
            '      Object.defineProperty(window,"top",{get:function(){return window;},configurable:true});\n'
            '    }else{window.top=window;}\n'
            '  }catch(e){try{window.top=window;}catch(e2){}}\n'
            '})();\n'
            'window.stop=function(){};\n'
            '</script>\n'
        )
        html = re.sub(r'<base[^>]*>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<head>', '<head>\n' + inject + f'\n<base href="{origin}/">', html, count=1, flags=re.IGNORECASE)
        html = re.sub(r'src="/', f'src="{origin}/', html)
        html = re.sub(r"src='/", f"src='{origin}/", html)
        html = re.sub(r'href="/', f'href="{origin}/', html)
        html = re.sub(r"href='/", f"href='{origin}/", html)
        html = html.replace(f'src="{origin}//', 'src="https://')
        html = html.replace(f"src='{origin}//", "src='https://")
        html = html.replace(f'href="{origin}//', 'href="https://')
        html = html.replace(f"href='{origin}//", "href='https://")
        html = re.sub(
            r'<script[^>]*>\s*if\s*\(\s*window\.parent\.frames\.length\s*>\s*0\s*\)\s*\{\s*window\.stop\(\);\s*\}\s*</script>',
            '', html, flags=re.IGNORECASE | re.DOTALL,
        )
        return HTMLResponse(content=html, media_type="text/html; charset=utf-8")

    if _is_player_domain(url):
        html = _wrap_player_page(html, url)
    else:
        html = html.replace('src="/', f'src="{parsed.scheme}://{parsed.netloc}/')
        html = html.replace("src='/", f"src='{parsed.scheme}://{parsed.netloc}/'")
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")


@router.get("/test-fetch")
async def test_fetch(url: str = Query(...)):
    curl_result = _curl_get_sync(url, retries=1, referer="https://livetv.sx/")
    urllib_result = _urllib_get_sync(url, referer="https://livetv.sx/")
    return {
        "url": url,
        "curl_len": len(curl_result) if curl_result else 0,
        "urllib_len": len(urllib_result) if urllib_result else 0,
        "curl_preview": curl_result[:200] if curl_result else "",
        "urllib_preview": urllib_result[:200] if urllib_result else "",
    }


@router.get("/hls-proxy")
async def hls_proxy(url: str = Query(..., description="m3u8 URL to proxy")):
    loop = asyncio.get_event_loop()
    content = await loop.run_in_executor(None, _curl_get_bytes, url, 2, settings.PUBLIC_API_URL.rstrip("/") + "/")
    if not content:
        return Response(status_code=502)

    is_segment = url.endswith(".ts") or url.endswith(".ts/") or ".ts?" in url
    if is_segment:
        return Response(
            content=content,
            media_type="video/mp2t",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=30",
            },
        )

    text = content.decode("utf-8", errors="ignore")
    parsed_orig = urlparse(url)
    orig_base = f"{parsed_orig.scheme}://{parsed_orig.netloc}"
    proxy_base = f"{settings.PUBLIC_API_URL.rstrip('/')}/api/proxy/hls-proxy"

    def rewrite_seg(seg_url: str) -> str:
        if seg_url.startswith("http"):
            return f"{proxy_base}?url={seg_url}"
        elif seg_url.startswith("//"):
            return f"{proxy_base}?url=https:{seg_url}"
        elif seg_url.startswith("/"):
            return f"{proxy_base}?url={orig_base}{seg_url}"
        else:
            base_path = "/".join(parsed_orig.path.rstrip("/").split("/")[:-1])
            return f"{proxy_base}?url={orig_base}{base_path}/{seg_url}"

    lines = text.strip().split("\n")
    rewritten = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            rewritten.append(rewrite_seg(stripped))
        else:
            rewritten.append(line)

    return Response(
        content="\n".join(rewritten),
        media_type="application/vnd.apple.mpegurl",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )
