from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    github_webhook_secret: str = ""
    webhook_service_url: str = "http://webhook:8001"

    class Config:
        env_file = ".env"
