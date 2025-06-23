from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables (.env)."""

    # OAuth
    CLIENT_ID: str | None = None
    CLIENT_SECRET: str | None = None
    REDIRECT_URI: str | None = "http://localhost:8000/auth/callback"
    YANDEX_AUTH_URL: str = "https://oauth.yandex.ru/authorize"
    YANDEX_TOKEN_URL: str = "https://oauth.yandex.ru/token"

    # Yandex Tracker
    TRACKER_TOKEN: str | None = None
    TRACKER_ORG_ID: str | None = None
    TRACKER_QUEUE: str | None = None

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/postgres"

    # Files
    UPLOAD_DIR: str = "uploaded_files"

    # Application
    ADMIN_LOGINS: str = "yakovleva.sv"  # comma-separated list of admin logins
    SECRET_KEY: str = "change-me"  # used to sign session cookies

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings() 