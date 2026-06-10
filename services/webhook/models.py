import uuid

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


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://neondb_owner:npg_lpJ0oW4UQzAL@ep-noisy-dust-aqasra2u-pooler.c-8.us-east-1.aws.neon.tech/neondb?sslmode=require"
    redis_url: str = "redis://redis:6379/0"
    qstash_token: str
    qstash_url: str = "https://qstash.upstash.io/v2/publish"
    orchestrator_service_url: str = "https://github-ai-pr-reviewer-orchestrator.onrender.com"
    learner_service_url: str = "https://github-ai-pr-reviewer-learner.onrender.com"

    class Config:
        env_file = ".env"
