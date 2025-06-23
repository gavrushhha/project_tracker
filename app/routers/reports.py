import os
import logging

from fastapi import APIRouter, Depends, Form, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import requests

from app.core.config import settings
from app.db.session import get_db
from app.models.report import Report
from app.core.templates import templates
from app.models.task import Task

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/submit", response_class=HTMLResponse)
async def submit_form(
    request: Request,
    username: str = Form(...),
    programs_supported: int = Form(...),
    projects_in_program: int = Form(...),
    new_scientists_employed: int = Form(...),
    department: str | None = Form(None),
    report_file: UploadFile = File(None),
    description: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Handle weekly report submission and push it to Tracker."""

    # Save uploaded file if provided
    file_path: str | None = None
    if report_file is not None:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        file_path = os.path.join(settings.UPLOAD_DIR, f"{username}_{report_file.filename}")
        with open(file_path, "wb") as f:
            f.write(await report_file.read())

    # Persist report in DB
    # placeholder; will update with issue_key / attachment later
    report = Report(
        username=username,
        programs_supported=programs_supported,
        projects_in_program=projects_in_program,
        new_scientists_employed=new_scientists_employed,
        file_path=file_path,
    )
    db.add(report)
    db.commit()

    # Ищем задачу, созданную администратором, в локальной таблице tasks
    task: Task | None = (
        db.query(Task)
        .filter(Task.assignee == username)
        .order_by(Task.created_at.desc())
        .first()
    )

    if task is None:
        raise HTTPException(status_code=404, detail="Не найдена назначенная задача для пользователя")

    issue_key = task.issue_key

    headers = {
        "Authorization": f"OAuth {settings.TRACKER_TOKEN}",
        "X-Org-ID": settings.TRACKER_ORG_ID,
    }

    # Comment text
    comment_text = (
        f"🔹 Новый отчёт от пользователя {username}:\n"
        f"- Поддержано программ: {programs_supported}\n"
        f"- Проектов в программе: {projects_in_program}\n"
        f"- Принято новых учёных: {new_scientists_employed}"
    )
    if description:
        comment_text += f"\n- Описание: {description}"

    comment_url = f"https://api.tracker.yandex.net/v3/issues/{issue_key}/comments"
    comment_resp = requests.post(comment_url, headers=headers, json={"text": comment_text})
    logger.info("Tracker comment response: %s - %s", comment_resp.status_code, comment_resp.text)
    if comment_resp.status_code != 201:
        raise HTTPException(status_code=500, detail=f"Ошибка добавления комментария: {comment_resp.text}")

    # Attach file if present
    if file_path:
        attach_url = f"https://api.tracker.yandex.net/v3/issues/{issue_key}/attachments"
        with open(file_path, "rb") as f:
            attach_resp = requests.post(
                attach_url,
                headers={
                    "Authorization": f"OAuth {settings.TRACKER_TOKEN}",
                    "X-Org-ID": settings.TRACKER_ORG_ID,
                },
                files={"file": (os.path.basename(file_path), f, "application/octet-stream")},
            )
        if attach_resp.status_code != 201:
            raise HTTPException(status_code=500, detail=f"Ошибка загрузки файла: {attach_resp.text}")

        attach_info = attach_resp.json()
        if isinstance(attach_info, list) and attach_info:
            last_att = attach_info[-1]
            report.attachment_id = str(last_att.get("id"))  # type: ignore[assignment]
            report.attachment_name = last_att.get("name") or os.path.basename(file_path)  # type: ignore[assignment]

    # store issue_key
    report.issue_key = issue_key  # type: ignore[assignment]

    # Move issue to "В работу" if possible
    transitions_url = f"https://api.tracker.yandex.net/v3/issues/{issue_key}/transitions"
    transitions_resp = requests.get(transitions_url, headers=headers)
    if transitions_resp.status_code == 200:
        transitions = transitions_resp.json()
        transition = next(
            (t for t in transitions if t["display"].lower() == "в работу"),
            None,
        )
        if transition:
            exec_url = (
                f"https://api.tracker.yandex.net/v3/issues/{issue_key}/transitions/{transition['id']}/_execute"
            )
            requests.post(exec_url, headers=headers, json={"comment": "Перевод в 'В работу'"})

    return templates.TemplateResponse(
        "success.html",
        {
            "request": request,
            "username": username,
            "issue_key": issue_key,
            "issue_url": f"https://tracker.yandex.ru/{issue_key}",
        },
    ) 