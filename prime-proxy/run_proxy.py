#!/usr/bin/env python3
"""Локальный прокси prime (1win) для hockey-live.

Схема: Render (US) -> cloudflared-туннель -> этот скрипт (РФ IP) -> 1win.
Плеер и m3u8 отдают контент только с российских IP, поэтому весь запрос
идёт через домашний компьютер.

Запуск: python run_proxy.py  (или двойной клик по run_proxy.bat)
"""
import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG_FILE = HERE / "proxy.log"
CONFIG_FILE = HERE / "config.json"
CLOUDFLARED = HERE / "cloudflared.exe"
LOCAL_PORT = 8899
CF_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

# Заголовки, с которыми браузер заходит на плеер 1win (Referer из белого списка)
PLAYER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://1wixpv.life/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Fetch-Dest": "iframe",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Upgrade-Insecure-Requests": "1",
}

_log_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    with _log_lock:
        print(line, flush=True)
        try:
            with LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


def _is_private_host(host: str) -> bool:
    """Запрещаем запросы во внутреннюю сеть (защита от SSRF)."""
    h = (host or "").lower().strip("[]")
    if h in ("localhost", "ip6-localhost"):
        return True
    if re.match(r"^127\.", h) or h.startswith("192.168.") or h.startswith("169.254."):
        return True
    if re.match(r"^10\.", h):
        return True
    m = re.match(r"^172\.(\d+)\.", h)
    if m and 16 <= int(m.group(1)) <= 31:
        return True
    if h in ("::1", "0:0:0:0:0:0:0:1"):
        return True
    return False


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # пишем в наш лог, не в stderr
        log(f"http {self.address_string()} {fmt % args}")

    def _send_bytes(self, data: bytes, status: int = 200, ctype: str = "application/octet-stream") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/health":
            self._send_bytes(b"ok", 200, "text/plain")
            return

        if "url" not in qs or not qs["url"]:
            self._send_bytes(b'{"error":"missing url"}', 400, "application/json")
            return

        target = qs["url"][0]
        try:
            u = urllib.parse.urlparse(target)
        except ValueError:
            self._send_bytes(b'{"error":"bad url"}', 400, "application/json")
            return
        if u.scheme not in ("http", "https") or not u.hostname:
            self._send_bytes(b'{"error":"bad url"}', 400, "application/json")
            return
        if _is_private_host(u.hostname):
            self._send_bytes(b'{"error":"private address forbidden"}', 403, "application/json")
            return

        req = urllib.request.Request(target, headers=PLAYER_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = resp.read()
                status = resp.status
                ctype = resp.headers.get("Content-Type") or "application/octet-stream"
            self._send_bytes(data, status, ctype)
        except urllib.error.HTTPError as e:
            try:
                data = e.read()
            except Exception:
                data = b""
            self._send_bytes(data, e.code, e.headers.get("Content-Type") or "text/plain")
        except Exception as e:
            log(f"forward error {target[:80]}: {type(e).__name__}: {e}")
            self._send_bytes(f'{{"error":"{type(e).__name__}"}}'.encode(), 502, "application/json")


def download_cloudflared() -> bool:
    if CLOUDFLARED.exists():
        return True
    url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    log(f"скачиваю cloudflared: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        CLOUDFLARED.write_bytes(data)
        log(f"cloudflared скачан ({len(data)} байт)")
        return True
    except Exception as e:
        log(f"скачивание cloudflared не удалось: {type(e).__name__}: {e}")
        return False


def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def render_update(url: str, config: dict) -> None:
    """Ставит PROXY_URL в Render и запускает деплой. Все ошибки — в лог."""
    key = (config.get("render_api_key") or "").strip()
    svc = (config.get("render_service_id") or "").strip()
    if not key or not svc:
        log("RENDER AUTO: ключей нет — вставь URL вручную (см. инструкцию выше)")
        return

    base = "https://api.render.com/v1"
    hdrs = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def call(method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, headers=hdrs, method=method)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")

    try:
        status, envs = call("GET", f"/services/{svc}/env-vars")
        if status != 200:
            log(f"RENDER AUTO: GET env-vars -> {status}")
            return
        items = envs.get("envVars") or envs.get("env_vars") or envs if isinstance(envs, list) else []
        found = next((e for e in items if e.get("key") == "PROXY_URL"), None)
        if found:
            st, _ = call("PATCH", f"/services/{svc}/env-vars/{found['id']}", {"value": url})
        else:
            st, _ = call("POST", f"/services/{svc}/env-vars", {"key": "PROXY_URL", "value": url})
        log(f"RENDER AUTO: PROXY_URL -> {st}")
        if st in (200, 201):
            try:
                dst, _ = call("POST", f"/services/{svc}/deploys", {})
                log(f"RENDER AUTO: деплой запущен -> {dst}")
            except Exception as e:
                log(f"RENDER AUTO: деплой не поднялся ({type(e).__name__}) — обнови вручную и нажми Deploy")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:300]
        except Exception:
            pass
        log(f"RENDER AUTO: ошибка {e.code}: {body}")
        log("Проверь render_api_key и render_service_id в config.json")
    except Exception as e:
        log(f"RENDER AUTO: {type(e).__name__}: {e}")


def ensure_config() -> dict:
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(
            json.dumps({"render_api_key": "", "render_service_id": ""}, indent=2),
            encoding="utf-8",
        )
    return load_config()


_current_url: str | None = None
_url_lock = threading.Lock()


def on_tunnel_url(url: str) -> None:
    global _current_url
    with _url_lock:
        if url == _current_url:
            return
        _current_url = url
    log("=" * 60)
    log(f"TUNNEL URL: {url}")
    log("Если Render не обновился сам — вставь этот URL вручную:")
    log("  Render -> backend -> Environment -> PROXY_URL -> Save")
    log("=" * 60)
    render_update(url, load_config())


def tunnel_loop() -> None:
    backoff = 3
    while True:
        if not download_cloudflared():
            time.sleep(60)
            continue
        log("запускаю cloudflared-туннель...")
        try:
            proc = subprocess.Popen(
                [str(CLOUDFLARED), "tunnel", "--url", f"http://localhost:{LOCAL_PORT}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as e:
            log(f"не смог запустить cloudflared: {e}")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        backoff = 3
        got_url = False
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                m = CF_URL_RE.search(line)
                if m:
                    got_url = True
                    on_tunnel_url(m.group(0))
                else:
                    log(f"cf| {line[:200]}")
        finally:
            try:
                proc.kill()
            except Exception:
                pass
        if not got_url:
            log("туннель не дал URL — перезапуск через 5 сек")
        else:
            log("cloudflared остановился — перезапуск через 5 сек")
        time.sleep(5)


def main() -> None:
    ensure_config()
    server = ThreadingHTTPServer(("127.0.0.1", LOCAL_PORT), ProxyHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log(f"локальный прокси: http://127.0.0.1:{LOCAL_PORT}")
    threading.Thread(target=tunnel_loop, daemon=True).start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        log("остановлен")


if __name__ == "__main__":
    sys.exit(main())
