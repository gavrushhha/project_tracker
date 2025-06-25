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
    # Basic fields (legacy/basic form)
    programs_supported: int | None = Form(None),
    projects_in_program: int | None = Form(None),
    new_scientists_employed: int | None = Form(None),

    # Extended form: dynamic lists
    publications_count: int | None = Form(None),
    pub_title: list[str] | None = Form(None),
    pub_doi: list[str] | None = Form(None),
    pub_relation: list[str] | None = Form(None),
    pub_file: list[UploadFile] | None = File(None),

    programs_count: int | None = Form(None),
    prog_name: list[str] | None = Form(None),
    prog_kind: list[str] | None = Form(None),
    prog_priority: list[str] | None = Form(None),
    prog_file: list[UploadFile] | None = File(None),

    events_count: int | None = Form(None),
    event_type: list[str] | None = Form(None),
    event_topic: list[str] | None = Form(None),
    event_file: list[UploadFile] | None = File(None),

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

    # Persist basic info; extended details can be stored later as JSON or separate tables
    report = Report(
        username=username,
        programs_supported=programs_supported or 0,
        projects_in_program=projects_in_program or 0,
        new_scientists_employed=new_scientists_employed or 0,
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

    comment_lines: list[str] = [f"🔹 Новый отчёт от пользователя {username}:"]
    if programs_supported is not None:
        comment_lines.append(f"- Поддержано программ: {programs_supported}")
    if projects_in_program is not None:
        comment_lines.append(f"- Проектов в программе: {projects_in_program}")
    if new_scientists_employed is not None:
        comment_lines.append(f"- Принято новых учёных: {new_scientists_employed}")

    # Publications details
    if pub_title:
        comment_lines.append("\n📚 Публикации:")
        for i, title in enumerate(pub_title):
            doi = pub_doi[i] if pub_doi and i < len(pub_doi) else ""
            relation = pub_relation[i] if pub_relation and i < len(pub_relation) else ""
            comment_lines.append(f"  • {title} (DOI: {doi}) – {relation}")

    # Education programs details
    if prog_name:
        comment_lines.append("\n🎓 Образовательные программы:")
        for i, name in enumerate(prog_name):
            kind = prog_kind[i] if prog_kind and i < len(prog_kind) else ""
            priority = prog_priority[i] if prog_priority and i < len(prog_priority) else ""
            comment_lines.append(f"  • {name} – {kind} – {priority}")

    # Events details
    if event_type:
        comment_lines.append("\n📅 Мероприятия:")
        for i, etype in enumerate(event_type):
            topic = event_topic[i] if event_topic and i < len(event_topic) else ""
            comment_lines.append(f"  • {etype}: {topic}")

    comment_text = "\n".join(comment_lines)
    if description:
        comment_text += f"\n- Описание: {description}"

    comment_url = f"https://api.tracker.yandex.net/v3/issues/{issue_key}/comments"
    comment_resp = requests.post(comment_url, headers=headers, json={"text": comment_text})
    logger.info("Tracker comment response: %s - %s", comment_resp.status_code, comment_resp.text)
    if comment_resp.status_code != 201:
        raise HTTPException(status_code=500, detail=f"Ошибка добавления комментария: {comment_resp.text}")

    def upload_to_tracker(file_path_local: str):
        attach_url_local = f"https://api.tracker.yandex.net/v3/issues/{issue_key}/attachments"
        with open(file_path_local, "rb") as f:
            return requests.post(
                attach_url_local,
                headers={
                    "Authorization": f"OAuth {settings.TRACKER_TOKEN}",
                    "X-Org-ID": settings.TRACKER_ORG_ID,
                },
                files={"file": (os.path.basename(file_path_local), f, "application/octet-stream")},
            )

    # Attach file(s) from basic file_path
    if file_path:
        attach_resp = upload_to_tracker(file_path)
        if attach_resp.status_code == 201 and isinstance(attach_resp.json(), list):
            last_att = attach_resp.json()[-1]
            report.attachment_id = str(last_att.get("id"))  # type: ignore[assignment]
            report.attachment_name = last_att.get("name") or os.path.basename(file_path)  # type: ignore[assignment]

    # Attach publication / program / event files
    multi_file_lists: list[list[UploadFile] | None] = [pub_file, prog_file, event_file]
    for up_files in multi_file_lists:
        if up_files:
            for uf in up_files:
                if not uf.filename:
                    continue
                tmp_path = os.path.join(settings.UPLOAD_DIR, uf.filename)
                with open(tmp_path, "wb") as tmp:
                    tmp.write(await uf.read())  # type: ignore[attr-defined]
                attach_resp = upload_to_tracker(tmp_path)
                # Если ещё не сохранена информация о приложении, сохраняем из первого успешно загруженного файла
                if (
                    attach_resp.status_code == 201
                    and isinstance(attach_resp.json(), list)
                    and report.attachment_id is None
                ):
                    first_att = attach_resp.json()[-1]
                    report.attachment_id = str(first_att.get("id"))  # type: ignore[assignment]
                    report.attachment_name = first_att.get("name") or uf.filename  # type: ignore[assignment]
                os.remove(tmp_path)

    # store issue_key
    report.issue_key = issue_key  # type: ignore[assignment]
    db.commit()

    # Move issue to "Нужна информация" after report submission
    transitions_url = f"https://api.tracker.yandex.net/v3/issues/{issue_key}/transitions"
    transitions_resp = requests.get(transitions_url, headers=headers)
    if transitions_resp.status_code == 200:
        transitions = transitions_resp.json()
        transition = next(
            (t for t in transitions if "нужна информация" in t["display"].lower()),
            None,
        )
        if transition:
            exec_url = (
                f"https://api.tracker.yandex.net/v3/issues/{issue_key}/transitions/{transition['id']}/_execute"
            )
            requests.post(exec_url, headers=headers)


    return templates.TemplateResponse(
        "success.html",
        {
            "request": request,
            "username": username,
            "issue_key": issue_key,
            "issue_url": f"https://tracker.yandex.ru/{issue_key}",
        },
    ) 