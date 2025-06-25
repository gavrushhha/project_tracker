from fastapi import APIRouter, HTTPException, Request, Depends, status as http_status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import requests

from app.core.config import settings
from app.db.session import get_db
from app.core.templates import templates
from app.models.task import Task
from app.core.security import get_current_user

router = APIRouter()


@router.get("/dashboard/{username}", response_class=HTMLResponse)
async def dashboard(
    username: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Display tracker task status for user. Only the owner can access."""

    if current_user.login != username:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Forbidden")

    can_submit = False
    issue_key: str | None = None
    issue_not_found = False
    status_display_val: str | None = None

    # Ищем задачи, созданные администратором, в локальной базе
    task: Task | None = (
        db.query(Task)
        .filter(Task.assignee == username)
        .order_by(Task.created_at.desc())
        .first()
    )

    if task is None:
        issue_not_found = True
    else:
        issue_key = str(task.issue_key)

    headers = {
        "Authorization": f"OAuth {settings.TRACKER_TOKEN}",
        "X-Org-ID": settings.TRACKER_ORG_ID,
        }

        # Получаем детали задачи для статуса
    try:
        resp = requests.get(f"https://api.tracker.yandex.net/v3/issues/{issue_key}", headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Tracker error: {resp.text}")

        issue = resp.json()
        status = issue.get("status", {})
        status_display_val = status.get("display") or status.get("name")
        status_name = (status_display_val or "").lower()
        # Пользователь не может сдавать отчёт только если задача уже "Закрыта"
        if status_name in ["in progress", "в работе"]:
            can_submit = True
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении статуса: {exc}") from exc

    # Всегда используем расширенную форму отчёта
    template_name = "dashboard_extended.html"

    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "username": username,
            "can_submit": can_submit,
            "issue_key": issue_key,
            "issue_not_found": issue_not_found,
            "status_display": status_display_val,
        },
    ) 
