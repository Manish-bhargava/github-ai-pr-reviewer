# import logging
# from contextlib import asynccontextmanager

# from fastapi import FastAPI, Request
# from sqlalchemy import select
# from sqlalchemy.ext.asyncio import (
#     AsyncSession,
#     async_sessionmaker,
#     create_async_engine,
# )

# from models import PullRequest, Settings
# from worker import analyze_pr, trigger_learning

# # ---------------- LOGGING ----------------

# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
# )

# logger = logging.getLogger("webhook-service")

# # ---------------- DB ----------------

# settings = Settings()

# engine = create_async_engine(
#     settings.database_url,
#     pool_pre_ping=True,
# )

# AsyncSessionLocal = async_sessionmaker(
#     engine,
#     class_=AsyncSession,
#     expire_on_commit=False,
# )

# # ---------------- LIFESPAN ----------------


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     logger.info("🚀 Webhook service starting...")
#     yield
#     await engine.dispose()
#     logger.info("🛑 Webhook service stopped")


# app = FastAPI(
#     title="Webhook Service",
#     lifespan=lifespan,
# )

# # ---------------- HEALTH ----------------


# @app.get("/health")
# async def health():
#     logger.info("Health check hit")
#     return {
#         "status": "ok",
#         "service": "webhook",
#     }


# # ---------------- MAIN WEBHOOK ----------------


# @app.post("/events", status_code=202)
# async def receive_event(request: Request):

#     body = await request.json()

#     event_type = request.headers.get(
#         "X-GitHub-Event",
#         "unknown",
#     )

#     logger.info("📩 EVENT RECEIVED: %s", event_type)
#     logger.info("📦 BODY: %s", body)

#     action = body.get("action", "")
#     pull_request = body.get("pull_request", {})

#     logger.info("⚡ ACTION: %s", action)

#     # ---------------- IGNORE NON PR EVENTS ----------------

#     if event_type != "pull_request":
#         logger.info(
#             "⛔ Ignoring non-PR event: %s",
#             event_type,
#         )
#         return {"status": "skipped"}

#     # ---------------- HANDLE MERGED PR ----------------

#     if action == "closed" and pull_request.get("merged"):

#         pr_number = pull_request.get("number")

#         repo_full_name = body.get(
#             "repository",
#             {},
#         ).get("full_name", "")

#         logger.info(
#             "✅ Merged PR detected: %s/%s",
#             repo_full_name,
#             pr_number,
#         )

#         async with AsyncSessionLocal() as session:

#             result = await session.execute(
#                 select(PullRequest).where(
#                     PullRequest.repo_full_name == repo_full_name,
#                     PullRequest.pr_number == pr_number,
#                 )
#             )

#             pr = result.scalar_one_or_none()

#             if pr:
#                 logger.info(
#                     "🧠 Triggering learning pipeline for PR id=%s",
#                     pr.id,
#                 )

#                 trigger_learning(
#                     repo_full_name=repo_full_name,
#                     pr_id=str(pr.id),
#                 )

#         return {"status": "accepted"}

#     # ---------------- HANDLE OPEN / UPDATE PR ----------------

#     if action not in (
#         "opened",
#         "reopened",
#         "synchronize",
#     ):
#         logger.info(
#             "⛔ Skipping unsupported action: %s",
#             action,
#         )
#         return {"status": "skipped"}

#     pr_number = pull_request.get("number")

#     repo_full_name = body.get(
#         "repository",
#         {},
#     ).get("full_name", "")

#     head_sha = (
#         pull_request.get("head", {})
#         .get("sha", "")
#     )

#     installation_id = body.get(
#         "installation",
#         {},
#     ).get("id", 0)

#     logger.info(
#         "🔍 PR EVENT: %s/%s @ %s",
#         repo_full_name,
#         pr_number,
#         head_sha,
#     )

#     async with AsyncSessionLocal() as session:

#         result = await session.execute(
#             select(PullRequest).where(
#                 PullRequest.repo_full_name == repo_full_name,
#                 PullRequest.pr_number == pr_number,
#                 PullRequest.head_sha == head_sha,
#             )
#         )

#         if result.scalar_one_or_none():
#             logger.info(
#                 "♻️ Already processing PR %s/%s",
#                 repo_full_name,
#                 pr_number,
#             )
#             return {
#                 "status": "already_processing",
#             }

#         pr_record = PullRequest(
#             repo_full_name=repo_full_name,
#             pr_number=pr_number,
#             head_sha=head_sha,
#             installation_id=installation_id,
#             status="pending",
#         )

#         session.add(pr_record)

#         await session.commit()
#         await session.refresh(pr_record)

#         pr_id = str(pr_record.id)

#         logger.info(
#             "💾 Saved PR in DB: %s",
#             pr_id,
#         )

#     # ---------------- TRIGGER QSTASH ----------------

#     analyze_pr(
#         pr_id=pr_id,
#         pr_number=pr_number,
#         repo_full_name=repo_full_name,
#         head_sha=head_sha,
#         installation_id=installation_id,
#     )

#     logger.info(
#         "🚀 Analysis queued via QStash for PR %s/%s",
#         repo_full_name,
#         pr_number,
#     )

#     return {"status": "accepted"}import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models import PullRequest, Settings
from worker import analyze_pr, trigger_learning

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook")

settings = Settings()

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Webhook starting")
    yield
    await engine.dispose()
    logger.info("🛑 Webhook stopped")


app = FastAPI(title="Webhook Service", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/events")
async def github_events(request: Request):
    body = await request.json()
    event = request.headers.get("X-GitHub-Event", "")

    if event != "pull_request":
        return {"skipped": True}

    action = body.get("action")
    pr = body.get("pull_request", {})

    repo = body.get("repository", {}).get("full_name")
    pr_number = pr.get("number")
    sha = pr.get("head", {}).get("sha")
    installation_id = body.get("installation", {}).get("id")

    # merged PR → learning
    if action == "closed" and pr.get("merged"):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PullRequest).where(
                    PullRequest.repo_full_name == repo,
                    PullRequest.pr_number == pr_number,
                )
            )
            pr_row = result.scalar_one_or_none()

            if pr_row:
                trigger_learning(repo, str(pr_row.id))

        return {"ok": True}

    # new PR → analyze
    if action in ("opened", "reopened", "synchronize"):

        async with AsyncSessionLocal() as session:
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

        analyze_pr(pr_id, pr_number, repo, sha, installation_id)

        return {"ok": True}

    return {"skipped": True}