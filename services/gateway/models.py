# models.py  —  Gateway Service
# DB models (mirrors webhook service) + Settings

import uuid

from pydantic_settings import BaseSettings
from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    Integer,
    Text,
    TIMESTAMP,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func


# ─── Settings ────────────────────────────────────────────────────────────────

class Settings(BaseSettings):
    # Webhook
    github_webhook_secret: str = ""

    # Internal service URLs
    webhook_service_url: str = ""
    reviewer_service_url: str = ""

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""

    # GitHub App name (used to build install URL)
    # e.g. if your app URL is github.com/apps/my-pr-reviewer → set "my-pr-reviewer"
    github_app_name: str = ""

    # Database (Neon PostgreSQL)
    # Must be asyncpg driver:
    # postgresql+asyncpg://user:pass@host/dbname
    database_url: str = ""

    # Frontend URL for CORS
    frontend_url: str = "http://localhost:5173"

    class Config:
        env_file = ".env"


# ─── SQLAlchemy Base ──────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ─── Models (same tables as webhook service — read-only from gateway) ─────────

class PullRequest(Base):
    __tablename__ = "pull_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_full_name = Column(Text, nullable=False)
    pr_number = Column(Integer, nullable=False)
    head_sha = Column(Text, nullable=False)
    installation_id = Column(BigInteger, nullable=False)
    status = Column(Text, nullable=False, server_default="pending")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class Finding(Base):
    __tablename__ = "findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pr_id = Column(UUID(as_uuid=True), ForeignKey("pull_requests.id"), nullable=True)
    file = Column(Text, nullable=True)
    line = Column(Integer, nullable=True)
    severity = Column(Text, nullable=True)
    message = Column(Text, nullable=True)
    agent = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class Pattern(Base):
    __tablename__ = "patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_full_name = Column(Text, nullable=False)
    pattern_text = Column(Text, nullable=False)
    frequency = Column(Integer, server_default="1")
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
