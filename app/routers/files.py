import os
import requests
from io import BytesIO
import zipfile

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


@router.get("/attachments/{issue_key}")
async def list_issue_attachments(issue_key: str):
    """Return list of attachments for given issue from Tracker."""
    headers = {
        "Authorization": f"OAuth {settings.TRACKER_TOKEN}",
        "X-Org-ID": settings.TRACKER_ORG_ID,
    }
    url = f"https://api.tracker.yandex.net/v3/issues/{issue_key}/attachments"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Не удалось получить список файлов")
    return resp.json()


@router.get("/attachments/{issue_key}/all.zip")
async def download_all_attachments_zip(issue_key: str):
    """Download all attachments of an issue as a single ZIP archive."""
    headers = {
        "Authorization": f"OAuth {settings.TRACKER_TOKEN}",
        "X-Org-ID": settings.TRACKER_ORG_ID,
    }
    list_url = f"https://api.tracker.yandex.net/v3/issues/{issue_key}/attachments"
    list_resp = requests.get(list_url, headers=headers)
    if list_resp.status_code != 200:
        raise HTTPException(status_code=list_resp.status_code, detail="Не удалось получить список файлов")
    attachments = list_resp.json()
    if not attachments:
        raise HTTPException(status_code=404, detail="Файлы не найдены")

    memory = BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as zf:
        for att in attachments:
            fid = att.get("id")
            fname = att.get("name") or str(fid)
            dl_url = f"https://api.tracker.yandex.net/v3/issues/{issue_key}/attachments/{fid}/{fname}"
            file_resp = requests.get(dl_url, headers=headers)
            if file_resp.status_code == 200:
                zf.writestr(fname, file_resp.content)
    memory.seek(0)
    return StreamingResponse(memory, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={issue_key}_attachments.zip"}) 