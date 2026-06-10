import asyncio
import logging
import time
from contextlib import asynccontextmanager

import httpx
import jwt
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from graph import build_graph
from models import AnalyzeRequest, Finding, Pattern, Settings

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
    logger.info("Orchestrator service starting")
    yield
    await engine.dispose()
    logger.info("Orchestrator service stopped")


app = FastAPI(title="Orchestrator Service", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "orchestrator"}
@app.post("/test")
async def test():
    print("QSTASH HIT THIS ENDPOINT")
    return {"status": "ok"}

# @app.post("/analyze", status_code=202)
# async def analyze(request: AnalyzeRequest):
#     logger.info("Analyzing PR %s/%s", request.repo_full_name, request.pr_number)

#     token = await get_installation_token(request.installation_id)
#     diff = await fetch_diff(request.repo_full_name, request.pr_number, token)

#     async with AsyncSessionLocal() as session:
#         result = await session.execute(
#             select(Pattern)
#             .where(Pattern.repo_full_name == request.repo_full_name)
#             .order_by(Pattern.frequency.desc())
#             .limit(10)
#         )
#         patterns = [row.pattern_text for row in result.scalars().all()]

#     state = await asyncio.to_thread(
#         build_graph().invoke,
#         {"diff": diff, "patterns": patterns, "findings": [], "deduplicated_findings": []},
#     )
#     findings_data = state.get("deduplicated_findings") or state.get("findings", [])
#     logger.info("Found %d findings for PR %s/%s", len(findings_data), request.repo_full_name, request.pr_number)

#     async with AsyncSessionLocal() as session:
#         for finding in findings_data:
#             session.add(
#                 Finding(
#                     pr_id=request.pr_id,
#                     file=finding.get("file"),
#                     line=finding.get("line"),
#                     severity=finding.get("severity"),
#                     message=finding.get("message"),
#                     agent=finding.get("agent"),
#                 )
#             )
#         await session.commit()

#     async with httpx.AsyncClient() as client:
#         response = await client.post(
#             f"{settings.reviewer_service_url}/post-review",
#             json={
#                 "pr_id": str(request.pr_id),
#                 "repo_full_name": request.repo_full_name,
#                 "pr_number": request.pr_number,
#                 "installation_id": request.installation_id,
#                 "findings": findings_data,
#             },
#             timeout=60,
#         )
#         response.raise_for_status()

#     logger.info("Review posted for PR %s/%s", request.repo_full_name, request.pr_number)
#     return {"status": "accepted", "findings_count": len(findings_data)}
@app.post("/learn")
async def learn(request):
    print("🔥 LEARN HIT")
    return {"ok": True}
@app.post("/analyze")
async def analyze(request):
    print("🔥 ANALYZE HIT")
    print(request)
    return {"ok": True}
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


async def fetch_diff(repo_full_name: str, pr_number: int, token: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3.diff",
            },
        )
        response.raise_for_status()
        return response.text
