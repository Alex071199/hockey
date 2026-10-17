from fastapi import APIRouter
from fastapi.responses import JSONResponse
import httpx

router = APIRouter(prefix="/api/app", tags=["app"])

GITHUB_LATEST_RELEASE = "https://api.github.com/repos/Alex071199/hockey/releases/latest"


@router.get("/version")
async def app_version():
    """Отдаёт последнюю версию Android TV приложения из GitHub Releases."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                GITHUB_LATEST_RELEASE,
                headers={"Accept": "application/vnd.github+json"},
            )
            if resp.status_code != 200:
                return JSONResponse(status_code=502, content={"error": "github unavailable"})
            data = resp.json()
            tag = data.get("tag_name", "")
            version = tag.lstrip("v") if tag else ""
            try:
                version_code = int(version)
            except ValueError:
                version_code = 0
            apk_url = None
            for asset in data.get("assets", []):
                if asset.get("name", "").endswith(".apk"):
                    apk_url = asset.get("browser_download_url")
                    break
            notes = data.get("body", "") or ""
            return {
                "version": version,
                "version_code": version_code,
                "apk_url": apk_url,
                "notes": notes[:500],
            }
    except Exception:
        return JSONResponse(status_code=500, content={"error": "version check failed"})
