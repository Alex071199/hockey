from fastapi import APIRouter, HTTPException
from pathlib import Path
import json

router = APIRouter(prefix="/api/app", tags=["app"])

RELEASE_FILE = Path(__file__).resolve().parents[2] / "latest_release.json"


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
