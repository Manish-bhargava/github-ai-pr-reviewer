import uuid

from pydantic import BaseModel
from pydantic_settings import BaseSettings
from sqlalchemy import TIMESTAMP, BigInteger, Column, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class PullRequest(Base):
    __tablename__ = "pull_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_full_name = Column(Text, nullable=False)
    pr_number = Column(Integer, nullable=False)
    head_sha = Column(Text, nullable=False)
    installation_id = Column(BigInteger, nullable=False)
    status = Column(Text, nullable=False, server_default="pending")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class ReviewRequest(BaseModel):
    pr_id: uuid.UUID
    repo_full_name: str
    pr_number: int
    installation_id: int
    findings: list[dict]


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://user:password@postgres:5432/codereviewer"
    github_app_id: str = ""
    github_app_private_key: str = ""

    class Config:
        env_file = ".env"
