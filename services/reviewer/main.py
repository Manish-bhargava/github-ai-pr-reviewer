import logging
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
import jwt
from fastapi import FastAPI
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models import PullRequest, ReviewRequest, Settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

settings = Settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Reviewer service starting")
    yield
    await engine.dispose()
    logger.info("Reviewer service stopped")


app = FastAPI(title="Reviewer Service", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "reviewer"}


def _finding_summary_line(finding: dict[str, Any]) -> str:
    severity = finding.get("severity", "info").upper()
    return (
        f"**[{severity}]** `{finding.get('file', 'unknown')}:{finding.get('line', '?')}` "
        f"({finding.get('agent', '')})\n{finding.get('message', '')}\n"
    )


def _build_summary(findings: list[dict[str, Any]]) -> str:
    lines = ["## AI Code Review\n"] + [_finding_summary_line(f) for f in findings]
    return "\n".join(lines)


@app.post("/post-review")
async def post_review(request: ReviewRequest):
    if not request.findings:
        logger.info("No findings for PR %s/%s; skipping GitHub review", request.repo_full_name, request.pr_number)
        return {"status": "ok", "skipped": True}

    token = await get_installation_token(request.installation_id)

    inline_comments = []
    for finding in request.findings:
        try:
            line = int(finding.get("line") or 0)
        except (ValueError, TypeError):
            line = 0
        if finding.get("file") and line > 0:
            inline_comments.append(
                {
                    "path": finding.get("file"),
                    "line": line,
                    "side": "RIGHT",
                    "body": (
                        f"**[{finding.get('severity', 'info').upper()}]** "
                        f"({finding.get('agent', '')})\n{finding.get('message', '')}"
                    ),
                }
            )

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    url = f"https://api.github.com/repos/{request.repo_full_name}/pulls/{request.pr_number}/reviews"
    summary = _build_summary(request.findings)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json={"event": "COMMENT", "body": summary, "comments": inline_comments},
            headers=headers,
            timeout=30,
        )
        if response.status_code == 422 and inline_comments:
            logger.warning("Inline comments rejected; posting summary-only review")
            response = await client.post(
                url,
                json={"event": "COMMENT", "body": summary},
                headers=headers,
                timeout=30,
            )
        response.raise_for_status()

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(PullRequest).where(PullRequest.id == request.pr_id).values(status="reviewed")
        )
        await session.commit()

    logger.info("Posted review for PR %s/%s", request.repo_full_name, request.pr_number)
    return {"status": "ok"}


async def get_installation_token(installation_id: int) -> str:
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 600, "iss": settings.github_app_id}
    private_key = settings.github_app_private_key.replace("\\n", "\n")
    encoded_jwt = jwt.encode(payload, private_key, algorithm="RS256")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {encoded_jwt}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        response.raise_for_status()
        return response.json()["token"]
