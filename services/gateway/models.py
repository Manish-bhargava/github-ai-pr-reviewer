
# models.py — Gateway Service

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # GitHub Webhook
    github_webhook_secret: str = ""

    # Internal Service URLs
    webhook_service_url: str = ""
    reviewer_service_url: str = ""

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""

    # GitHub App
    github_app_name: str = ""

    # Database
    database_url: str = ""

    # Frontend
    frontend_url: str = "http://localhost:5173"

    class Config:
        env_file = ".env"

