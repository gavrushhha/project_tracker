from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import List
import requests
from sqlalchemy.orm import Session

from app.core.security import admin_required
from app.core.config import settings
from app.core.templates import templates
from app.db.session import get_db
from app.models.task import Task

router = APIRouter(prefix="/admin/batch", tags=["admin-batch"], dependencies=[Depends(admin_required)])

# Pydantic schemas
class SingleTask(BaseModel):
    queue: str = Field(..., description="Queue key")
    assignee: str = Field(..., description="User login")

class BatchTasksSchema(BaseModel):
    summary: str
    form_type: str = Field(..., pattern="^(basic|extended)$", description="Тип формы: basic или extended")
    tasks: List[SingleTask]


@router.get("/", response_class=HTMLResponse)
async def batch_form(request: Request):
    """Render wizard page for creating multiple tasks."""
    return templates.TemplateResponse("admin_batch.html", {"request": request})


@router.post("/tasks")
async def create_batch_tasks(data: BatchTasksSchema, db: Session = Depends(get_db)):
    headers = {
        "Authorization": f"OAuth {settings.TRACKER_TOKEN}",
        "X-Org-ID": settings.TRACKER_ORG_ID,
        "Content-Type": "application/json",
    }
    created: list[str] = []
    for item in data.tasks:
        # Всегда используем расширенную форму – ссылка без дополнительных параметров
        link = f"https://report.siriusuniversity.ru/dashboard/{item.assignee}"

        payload = {
            "queue": item.queue,
            "summary": data.summary,
            "description": f"Перейдите по ссылке для заполнения: {link}",
            "type": "task",
            "assignee": item.assignee,
            "priority": {"id": "3"},
        }
        resp = requests.post("https://api.tracker.yandex.net/v3/issues/", headers=headers, json=payload)
        if resp.status_code == 201:
            issue_json = resp.json()
            issue_key = issue_json["key"]
            created.append(issue_key)


            # Переводим задачу в статус «В работу», если такой переход доступен
            transitions_url = f"https://api.tracker.yandex.net/v3/issues/{issue_key}/transitions"
            trans_resp = requests.get(transitions_url, headers=headers)
            if trans_resp.status_code == 200:
                transitions = trans_resp.json()
                transition = next((t for t in transitions if t.get("display", "").lower() == "в работу"), None)
                if transition:
                    exec_url = (
                        f"https://api.tracker.yandex.net/v3/issues/{issue_key}/transitions/{transition['id']}/_execute"
                    )
                    requests.post(exec_url, headers=headers, json={"comment": "Статус установлен автоматически"})

            # Сохраняем в БД для дашборда
            db_task = Task(
                issue_key=issue_key,
                queue_key=item.queue,
                assignee=item.assignee,
                summary=data.summary,
                form_type=data.form_type,
            )
            db.add(db_task)
            db.commit()
        
        else:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return {"created": created} 
