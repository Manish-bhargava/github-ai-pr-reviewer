from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    github_webhook_secret: str = ""
    webhook_service_url: str = "https://github-ai-pr-reviewer-webhook.onrender.com"

    class Config:
        env_file = ".env"
