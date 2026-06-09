import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models import Finding, LearnRequest, Pattern, Settings

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
    logger.info("Learner service starting")
    yield
    await engine.dispose()
    logger.info("Learner service stopped")


app = FastAPI(title="Learner Service", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "learner"}


@app.post("/learn")
async def learn(request: LearnRequest):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Finding).where(
                Finding.pr_id == request.pr_id,
                Finding.severity.in_(["warning", "error"]),
            )
        )
        findings = result.scalars().all()
        logger.info("Learning from %d findings for PR %s", len(findings), request.pr_id)

        for finding in findings:
            stmt = (
                insert(Pattern)
                .values(
                    repo_full_name=request.repo_full_name,
                    pattern_text=finding.message,
                    frequency=1,
                )
                .on_conflict_do_update(
                    index_elements=["repo_full_name", "pattern_text"],
                    set_={
                        "frequency": Pattern.frequency + 1,
                        "updated_at": func.now(),
                    },
                )
            )
            await session.execute(stmt)

        await session.commit()

    return {"status": "ok", "patterns_updated": len(findings)}
