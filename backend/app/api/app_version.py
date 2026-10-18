from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import json

router = APIRouter(prefix="/api/app", tags=["app"])

RELEASE_FILE = Path(__file__).resolve().parents[2] / "latest_release.json"
APK_FILE = Path(__file__).resolve().parents[2] / "static" / "HockeyLiveTV.apk"


@router.get("/apk")
async def app_apk():
    """Отдаёт APK Android TV приложения для обновления по воздуху."""
    if not APK_FILE.exists():
        raise HTTPException(status_code=404, detail="apk not found")
    return FileResponse(
        APK_FILE,
        media_type="application/vnd.android.package-archive",
        filename="HockeyLiveTV.apk",
    )



@router.get("/version")
async def app_version():
    """Отдаёт последнюю версию Android TV приложения."""
    try:
        data = json.loads(RELEASE_FILE.read_text(encoding="utf-8"))
        return {
            "version": str(data.get("version", "")),
            "version_code": int(data.get("version_code", 0)),
            "apk_url": data.get("apk_url"),
            "notes": str(data.get("notes", ""))[:500],
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="release file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
