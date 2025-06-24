from fastapi import APIRouter, Request, Depends, HTTPException, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
import secrets
import httpx
from pydantic import BaseModel

from app.core.config import settings
from app.db.session import get_db
from app.models.report import Report
from app.models.user import User
from app.core.templates import templates
from app.core.security import issue_session_cookie, normalize_login

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render Yandex OAuth login page with parameters required by YaAuthSuggest."""

    # Build the redirect URI for the auxiliary page that receives the OAuth token.
    token_redirect_uri = request.url_for("suggest_token")

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "client_id": settings.CLIENT_ID,
            "token_redirect_uri": token_redirect_uri,
        },
    )


@router.get("/login")
async def login():
    """Redirect user to Yandex OAuth with CSRF-safe `state` parameter and `redirect_uri`."""

    state = secrets.token_urlsafe(16)
    params = (
        f"response_type=code"
        f"&client_id={settings.CLIENT_ID}"
        f"&redirect_uri={settings.REDIRECT_URI}"
        f"&state={state}"
    )
    url = f"{settings.YANDEX_AUTH_URL}?{params}"

    response = RedirectResponse(url)
    # Сохраняем state в http-only cookie на 5 минут
    response.set_cookie("oauth_state", state, httponly=True, max_age=300)
    return response


@router.get("/auth/code-callback")
async def auth_code_callback(
    code: str,
    state: str | None = None,
    oauth_state: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    """Обрабатываем callback, проверяем `state`, получаем токен, сохраняем в cookie."""

    # CSRF-check
    if state is None or oauth_state is None or state != oauth_state:
        raise HTTPException(status_code=400, detail="Некорректный OAuth state")

    # Обмениваем code на токен
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            settings.YANDEX_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.CLIENT_ID,
                "client_secret": settings.CLIENT_SECRET,
                "redirect_uri": settings.REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    token_data = response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Не удалось получить токен")

    # Получаем информацию о пользователе через Tracker API
    headers = {
        "Authorization": f"OAuth {access_token}",
        "X-Org-ID": settings.TRACKER_ORG_ID,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        user_response = await client.get("https://api.tracker.yandex.net/v3/myself", headers=headers)

    if user_response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid token for Tracker")

    user_data = user_response.json()
    username = normalize_login(user_data.get("login"))
    if not username:
        raise HTTPException(status_code=400, detail="Unable to retrieve login")

    # ensure user exists
    user = db.query(User).filter(User.login == username).first()
    if not user:
        user = User(login=username, is_admin=username in settings.ADMIN_LOGINS.split(","))
        db.add(user)
    # create report user row (legacy) if missing
    if not db.query(Report).filter(Report.username == username).first():
        db.add(Report(username=username))
    db.commit()

    # Redirect admins to admin dashboard immediately
    target_url = "/admin" if bool(user.is_admin) else f"/dashboard/{username}"
    redirect = RedirectResponse(url=target_url)
    # Создаём подписанную сессию
    issue_session_cookie(redirect, username)
    # Удаляем временный oauth_state cookie
    redirect.delete_cookie("oauth_state")
    return redirect


class TokenLogin(BaseModel):
    access_token: str


@router.post("/auth/token-login")
async def token_login(payload: TokenLogin, db: Session = Depends(get_db)):
    """Login flow for Yandex JS widget: receives access_token, validates and issues cookie."""

    access_token = payload.access_token
    # validate token via Tracker API /myself
    headers = {
        "Authorization": f"OAuth {access_token}",
        "X-Org-ID": settings.TRACKER_ORG_ID,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get("https://api.tracker.yandex.net/v3/myself", headers=headers)

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid token")

    username = normalize_login(resp.json().get("login"))
    if not username:
        raise HTTPException(status_code=400, detail="Unable to retrieve login")

    # ensure user exists
    user = db.query(User).filter(User.login == username).first()
    if not user:
        user = User(login=username, is_admin=username in settings.ADMIN_LOGINS.split(","))
        db.add(user)
        db.commit()
    # Redirect admins to admin dashboard immediately
    target_url = "/admin" if bool(user.is_admin) else "/dashboard/" + username
    response = RedirectResponse(url=target_url, status_code=303)
    issue_session_cookie(response, username)
    return response


# --- Instant auth auxiliary page -------------------------------------------------


@router.get("/auth/callback", name="suggest_token", response_class=HTMLResponse)
async def suggest_token_page(request: Request):
    """Auxiliary blank page that receives the access_token hash from YaAuthSuggest.

    The included sdk-suggest-token script parses the token from the URL fragment
    and passes it to the opener / parent origin.
    """

    return templates.TemplateResponse(
        "suggest_token.html",
        {
            "request": request,
        },
    ) 