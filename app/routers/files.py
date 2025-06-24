import os
import requests

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from app.core.config import settings

router = APIRouter()


@router.get("/files/{filename}")
async def download_file(filename: str):
    """Return uploaded file by name."""
    file_path = os.path.join("uploaded_files", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="application/octet-stream", filename=filename)
    raise HTTPException(status_code=404, detail="Файл не найден") 


# --- Proxy download from Yandex Tracker ---


@router.get("/attachments/{issue_key}/{attachment_id}/{filename:path}")
async def download_tracker_attachment(issue_key: str, attachment_id: str, filename: str):
    """Proxy file download from Tracker attachments API, preserving auth headers."""

    url = (
        f"https://api.tracker.yandex.net/v3/issues/{issue_key}/attachments/{attachment_id}/{filename}"
    )
    headers = {
        "Authorization": f"OAuth {settings.TRACKER_TOKEN}",
        "X-Org-ID": settings.TRACKER_ORG_ID,
    }
    resp = requests.get(url, headers=headers, stream=True)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Не удалось скачать файл")

    return StreamingResponse(resp.iter_content(chunk_size=8192),
                             media_type=resp.headers.get("Content-Type", "application/octet-stream"),
                             headers={"Content-Disposition": f"attachment; filename={filename}"}) 