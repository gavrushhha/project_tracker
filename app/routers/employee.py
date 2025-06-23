from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from app.core.templates import templates
import requests

from app.core.security import get_current_user
from app.core.config import settings

router = APIRouter(prefix="/employee", tags=["employee"])


@router.get("/tasks", response_class=HTMLResponse)
async def list_tasks(request: Request, current_user = Depends(get_current_user)):
    """Show list of tasks assigned to current employee from Tracker."""
    headers = {
        "Authorization": f"OAuth {settings.TRACKER_TOKEN}",
        "X-Org-ID": settings.TRACKER_ORG_ID,
        "Content-Type": "application/json",
    }
    query = {
        "query": f"assignee: {current_user.login} AND queue: {settings.TRACKER_QUEUE} AND status:!closed"
    }
    resp = requests.post("https://api.tracker.yandex.net/v3/issues/_search", headers=headers, json=query)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    issues = resp.json()
    return templates.TemplateResponse(
        "employee_tasks.html",
        {"request": request, "issues": issues, "username": current_user.login},
    ) 