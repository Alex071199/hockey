"""Probe: проверка доступности 1win-трансляции из этого региона (регион sin)."""
import re
import time

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

app = FastAPI(title="winprobe")

WIN_ORIGIN = "https://1wixpv.life"
WIN_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
PLAYER_HEADERS = {
    "User-Agent": WIN_UA,
    "Referer": WIN_ORIGIN + "/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Sec-Fetch-Dest": "iframe",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Upgrade-Insecure-Requests": "1",
}


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/probe")
async def probe(url: str = Query(..., description="broadcast.url из WS")):
    out: dict = {"ok": False}
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as c:
            r = await c.get(url, headers=PLAYER_HEADERS)
    except Exception as e:
        out["error"] = f"player: {e}"
        return out
    out["player"] = {
        "status": r.status_code,
        "len": len(r.content),
        "ms": int((time.time() - t0) * 1000),
        "geo_block": "недоступно в вашем регионе" in r.text,
    }
    m = re.search(r"https://[^'\"\s]+\.m3u8[^'\"\s]*", r.text)
    if not m:
        out["preview"] = r.text[:600]
        return out
    m3u8 = m.group(0).rstrip("'\";,")
    out["m3u8"] = m3u8

    async with httpx.AsyncClient(timeout=25) as c:
        r1 = await c.get(m3u8, headers={"User-Agent": WIN_UA})
        out["master"] = {"status": r1.status_code, "len": len(r1.content)}
        if r1.status_code != 200:
            return out
        lines = [l.strip() for l in r1.text.splitlines() if l.strip() and not l.startswith("#")]
        if not lines:
            out["master_empty"] = True
            return out
        import urllib.parse as up

        variant = up.urljoin(m3u8, lines[0])
        r2 = await c.get(variant, headers={"User-Agent": WIN_UA})
        out["variant"] = {"status": r2.status_code, "len": len(r2.content)}
        if r2.status_code != 200:
            return out
        segs = [l.strip() for l in r2.text.splitlines() if l.strip() and not l.startswith("#")]
        if not segs:
            out["variant_empty"] = True
            return out
        seg = up.urljoin(variant, segs[-1])
        r3 = await c.get(seg, headers={"User-Agent": WIN_UA})
        out["segment"] = {"status": r3.status_code, "len": len(r3.content), "head": r3.content[:4].hex()}
    out["ok"] = r3.status_code == 200 and len(r3.content) > 1000
    out["total_ms"] = int((time.time() - t0) * 1000)
    return out


@app.get("/upstream")
async def upstream(url: str = Query(...)):
    """Заготовка будущего прокси: отдаёт ответ эджа как есть."""
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.get(url, headers={"User-Agent": WIN_UA})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    return JSONResponse(
        {"status": r.status_code, "len": len(r.content)},
        status_code=200,
    )
