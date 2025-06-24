from fastapi import Depends, HTTPException, Cookie, status
from sqlalchemy.orm import Session
from itsdangerous import TimestampSigner, BadSignature, SignatureExpired

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User


signer = TimestampSigner(settings.SECRET_KEY)


def _create_session_cookie(login: str) -> str:
    """Return signed value for Set-Cookie."""
    return signer.sign(login.encode()).decode()


def _verify_session_cookie(value: str) -> str | None:
    try:
        raw = signer.unsign(value, max_age=3600).decode()
        return raw
    except (BadSignature, SignatureExpired):
        return None


async def get_current_user(
    session: str | None = Cookie(None, alias="session"),
    db: Session = Depends(get_db),
) -> User:
    """Dependency to fetch user by signed session cookie."""

    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    login = _verify_session_cookie(session)
    if not login:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    user = db.query(User).filter(User.login == login).first()
    if not user:
        # Should not normally happen – create record lazily
        user = User(login=login)  # login already normalized when session issued
        db.add(user)

    # ensure admin flag sync with settings each time
    expected_admin = login in settings.ADMIN_LOGINS.split(",") if settings.ADMIN_LOGINS else False
    if bool(user.is_admin) != expected_admin:
        setattr(user, "is_admin", expected_admin)
    db.commit()

    return user


def admin_required(current_user: User = Depends(get_current_user)) -> User:
    if not bool(current_user.is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return current_user 


# Helper exposed for auth router
def issue_session_cookie(response, login: str):
    """Attach signed session cookie to response."""
    response.set_cookie(
        "session",
        _create_session_cookie(login),
        httponly=True,
        max_age=3600,
        samesite="lax",
    )


def normalize_login(login: str) -> str:
    """Return login without domain part (before '@')."""
    return login.split('@')[0] if '@' in login else login


# duplicate definitions removed – keep code above as single source of truth 