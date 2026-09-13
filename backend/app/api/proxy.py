import asyncio
import re
import shutil
import subprocess
import time
from urllib.parse import urlparse

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/api/proxy", tags=["proxy"])

CURL = shutil.which("curl") or "curl"
_cache: dict[str, tuple[float, str]] = {}
CACHE_TTL = 300


def _curl_get_sync(url: str, retries: int = 2) -> str:
    for attempt in range(retries):
        try:
            cmd = [
                CURL, "-s", "-k", "-L",
                "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "--connect-timeout", "8",
                "--max-time", "15",
                url,
            ]
            r = subprocess.run(cmd, capture_output=True, timeout=20)
            if r.stdout and len(r.stdout) > 100:
                return r.stdout.decode("utf-8", errors="ignore")
        except Exception:
            pass
    return ""


async def _fetch_page(url: str) -> str:
    cached = _cache.get(url)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]
    loop = asyncio.get_event_loop()
    html = await loop.run_in_executor(None, _curl_get_sync, url, 2)
    if html:
        _cache[url] = (time.time(), html)
    return html


def _resolve_url(src: str, base_url: str) -> str:
    if src.startswith("//"):
        return "https:" + src
    elif src.startswith("/"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{src}"
    return src


def _extract_iframes(html: str) -> list[str]:
    return re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)


def _make_clean_player(player_url: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ margin: 0; padding: 0; background: #000; overflow: hidden; }}
  iframe {{ width: 100%; height: 100vh; border: none; }}
</style>
</head>
<body>
<iframe src="{player_url}" allowfullscreen="true" allow="autoplay; encrypted-media; gyroscope; picture-in-picture"></iframe>
</body>
</html>"""


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
  <p>Источник видео недоступен. Вероятно, он заблокирован вашим провайдером
     (livetv / onhockey часто блокируют по SNI).</p>
  <p>Включите VPN и обновите страницу, либо выберите другой источник
     (VK, Rutube, OK, Ace Stream).</p>
</div></body></html>"""


@router.get("/stream")
async def proxy_stream(url: str = Query(..., description="Stream page URL")):
    is_livetv = "livetv903.me" in url or "livetv.sx" in url
    parsed = urlparse(url)

    if is_livetv:
        result = await _resolve_livetv_player(url)
        if result:
            return HTMLResponse(content=result, media_type="text/html; charset=utf-8")

    html = await _fetch_page(url)
    if not html:
        return HTMLResponse(_failed_page(), media_type="text/html; charset=utf-8", status_code=502)

    html = html.replace('src="/', f'src="{parsed.scheme}://{parsed.netloc}/')
    html = html.replace("src='/", f"src='{parsed.scheme}://{parsed.netloc}/")
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")


async def _resolve_livetv_player(webplayer_url: str) -> str | None:
    html = await _fetch_page(webplayer_url)
    if not html:
        return None

    iframes = _extract_iframes(html)
    if not iframes:
        return None

    ad_skip = {"ads", "banner", "getbanner", "adskeeper"}
    player_url = None
    for src in iframes:
        if not any(p in src.lower() for p in ad_skip):
            player_url = _resolve_url(src, webplayer_url)
            break

    if not player_url:
        return None

    inner_html = await _fetch_page(player_url)
    if not inner_html:
        return _make_clean_player(player_url)

    inner_iframes = _extract_iframes(inner_html)
    clean = [f for f in inner_iframes if not any(p in f.lower() for p in ad_skip)]

    if clean:
        final_url = _resolve_url(clean[0], player_url)
        return _make_clean_player(final_url)

    return _make_clean_player(player_url)
