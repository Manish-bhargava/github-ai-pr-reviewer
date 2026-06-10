import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from models import PullRequest, Settings
from worker import analyze_pr, trigger_learning

# ---------------- LOGGING ----------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("webhook")

# ---------------- DB ----------------

settings = Settings()

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ---------------- LIFESPAN ----------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Webhook service starting")
    yield
    await engine.dispose()
    logger.info("🛑 Webhook service stopped")


app = FastAPI(
    title="Webhook Service",
    lifespan=lifespan,
)

# ---------------- HEALTH ----------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "webhook",
    }


# ---------------- GITHUB WEBHOOK ----------------

@app.post("/events", status_code=202)
async def github_events(request: Request):
    body = await request.json()

    event = request.headers.get(
        "X-GitHub-Event",
        "",
    )

    logger.info("📩 GitHub Event: %s", event)

    if event != "pull_request":
        return {"status": "skipped"}

    action = body.get("action")
    pr = body.get("pull_request", {})

    repo = body.get("repository", {}).get("full_name")
    pr_number = pr.get("number")
    sha = pr.get("head", {}).get("sha")
    installation_id = body.get("installation", {}).get("id")

    logger.info(
        "📦 Action=%s Repo=%s PR=%s",
        action,
        repo,
        pr_number,
    )

    # ---------------- MERGED PR ----------------

    if action == "closed" and pr.get("merged"):

        logger.info("✅ Merged PR detected")

        async with AsyncSessionLocal() as session:

            result = await session.execute(
                select(PullRequest).where(
                    PullRequest.repo_full_name == repo,
                    PullRequest.pr_number == pr_number,
                )
            )

            pr_row = result.scalar_one_or_none()

            if pr_row:
                trigger_learning(
                    repo_full_name=repo,
                    pr_id=str(pr_row.id),
                )

        return {"status": "accepted"}

    # ---------------- OPENED / UPDATED PR ----------------

    if action in (
        "opened",
        "reopened",
        "synchronize",
    ):

        async with AsyncSessionLocal() as session:

            result = await session.execute(
                select(PullRequest).where(
                    PullRequest.repo_full_name == repo,
                    PullRequest.pr_number == pr_number,
                    PullRequest.head_sha == sha,
                )
            )

            existing = result.scalar_one_or_none()

            if existing:
                logger.info("♻️ Already processed")
                return {"status": "already_processing"}

            pr_row = PullRequest(
                repo_full_name=repo,
                pr_number=pr_number,
                head_sha=sha,
                installation_id=installation_id,
                status="pending",
            )

            session.add(pr_row)

            await session.commit()
            await session.refresh(pr_row)

            pr_id = str(pr_row.id)

            logger.info("💾 Saved PR %s", pr_id)

        response = analyze_pr(
            pr_id=pr_id,
            pr_number=pr_number,
            repo_full_name=repo,
            head_sha=sha,
            installation_id=installation_id,
        )

        logger.info(
            "🚀 QStash Message Published: %s",
            response,
        )

        return {"status": "accepted"}

    return {"status": "skipped"}