# main.py  —  Gateway Service
# Handles: webhook forwarding + all frontend API endpoints
# DB: PostgreSQL via SQLAlchemy async + Neon

import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from typing import List, Optional
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from models import Finding, PullRequest, Settings
from schemas import (
    DashboardStats,
    RepositoryInfo,
    RepositoryDetail,
    PRItem,
    ReviewListItem,
    ReviewDetail,
    GitHubInstallUrl,
)

# ─── Logging ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Settings ────────────────────────────────────────────────────────────────

settings = Settings()

# ─── Database ────────────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


# ─── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Gateway Service starting")
    yield
    await engine.dispose()
    logger.info("🛑 Gateway Service stopped")


# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="Gateway Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health / Root ────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "service": "gateway",
        "status": "running",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway"}


# ─── GitHub Webhook (forward to webhook service) ──────────────────────────────

@app.post("/webhook/github")
async def github_webhook(request: Request):
    body = await request.body()
    signature_header = request.headers.get("X-Hub-Signature-256", "")

    if not settings.github_webhook_secret:
        logger.error("GITHUB_WEBHOOK_SECRET not configured")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    secret = settings.github_webhook_secret.encode()
    generated_signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    expected_signature = f"sha256={generated_signature}"

    if not hmac.compare_digest(expected_signature, signature_header):
        logger.warning("Invalid GitHub webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    webhook_url = f"{settings.webhook_service_url}/events"
    logger.info("Forwarding webhook to %s", webhook_url)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": request.headers.get("X-GitHub-Event", ""),
                },
                timeout=30,
            )
            response.raise_for_status()
    except Exception as e:
        logger.exception("Failed to forward webhook")
        raise HTTPException(status_code=500, detail=str(e))

    logger.info("GitHub webhook forwarded successfully")
    return {"status": "ok"}


# ─── GitHub App Install URL ───────────────────────────────────────────────────

@app.get("/api/github/install-url", response_model=GitHubInstallUrl)
async def get_install_url():
    """Returns the GitHub App installation URL for the frontend Connect button."""
    if not settings.github_app_name:
        raise HTTPException(status_code=500, detail="GITHUB_APP_NAME not configured")
    url = f"https://github.com/apps/{settings.github_app_name}/installations/new"
    return {"url": url}


# ─── Dashboard Stats ──────────────────────────────────────────────────────────

@app.get("/api/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """
    Summary counts for the dashboard stat cards.
    - repositories  : distinct repos that have at least one PR
    - prs_reviewed  : PRs with status = 'completed'
    - reviews_generated : total findings count
    - open_prs      : PRs with status = 'pending' or 'processing'
    """
    total_repos_result = await db.execute(
        select(func.count(func.distinct(PullRequest.repo_full_name)))
    )
    total_repos = total_repos_result.scalar() or 0

    prs_reviewed_result = await db.execute(
        select(func.count()).where(PullRequest.status == "completed")
    )
    prs_reviewed = prs_reviewed_result.scalar() or 0

    reviews_generated_result = await db.execute(
        select(func.count()).select_from(Finding)
    )
    reviews_generated = reviews_generated_result.scalar() or 0

    open_prs_result = await db.execute(
        select(func.count()).where(PullRequest.status.in_(["pending", "processing"]))
    )
    open_prs = open_prs_result.scalar() or 0

    return DashboardStats(
        repositories=total_repos,
        prs_reviewed=prs_reviewed,
        reviews_generated=reviews_generated,
        open_prs=open_prs,
    )


# ─── Repositories ────────────────────────────────────────────────────────────

@app.get("/api/repositories", response_model=List[RepositoryInfo])
async def list_repositories(db: AsyncSession = Depends(get_db)):
    """
    Returns one row per distinct repo_full_name with latest review date.
    """
    result = await db.execute(
        select(
            PullRequest.repo_full_name,
            func.max(PullRequest.created_at).label("last_review"),
            func.max(PullRequest.status).label("status"),
        ).group_by(PullRequest.repo_full_name)
        .order_by(func.max(PullRequest.created_at).desc())
    )
    rows = result.all()

    repos = []
    for i, row in enumerate(rows):
        # Use row index as a stable numeric id for the frontend URL
        last_review_str = (
            row.last_review.strftime("%Y-%m-%d") if row.last_review else None
        )
        # Determine display status
        status = "active" if row.status == "completed" else "pending"
        repos.append(
            RepositoryInfo(
                id=i + 1,
                name=row.repo_full_name,
                status=status,
                last_review=last_review_str,
            )
        )
    return repos


@app.get("/api/repositories/{owner}/{repo}/prs", response_model=List[PRItem])
async def get_repository_prs(owner: str, repo: str, db: AsyncSession = Depends(get_db)):
    """
    Returns all pull requests for a specific repo (owner/repo).
    """
    repo_full_name = f"{owner}/{repo}"

    result = await db.execute(
        select(PullRequest)
        .where(PullRequest.repo_full_name == repo_full_name)
        .order_by(PullRequest.created_at.desc())
    )
    prs = result.scalars().all()

    if not prs:
        raise HTTPException(status_code=404, detail=f"No PRs found for {repo_full_name}")

    return [
        PRItem(
            number=pr.pr_number,
            title=f"PR #{pr.pr_number} — {pr.head_sha[:7]}",
            status=pr.status,
            created_at=pr.created_at.strftime("%Y-%m-%d") if pr.created_at else None,
        )
        for pr in prs
    ]


@app.get("/api/repositories/{owner}/{repo}", response_model=RepositoryDetail)
async def get_repository_detail(owner: str, repo: str, db: AsyncSession = Depends(get_db)):
    """
    Returns stats for a specific repo. Used on the Repository Details page.
    """
    repo_full_name = f"{owner}/{repo}"

    result = await db.execute(
        select(PullRequest).where(PullRequest.repo_full_name == repo_full_name)
    )
    prs = result.scalars().all()

    if not prs:
        raise HTTPException(status_code=404, detail=f"Repository {repo_full_name} not found")

    total_reviews = sum(1 for p in prs if p.status == "completed")
    open_prs = sum(1 for p in prs if p.status in ("pending", "processing"))
    closed_prs = sum(1 for p in prs if p.status in ("completed", "failed"))

    return RepositoryDetail(
        id=1,
        name=repo_full_name,
        total_reviews=total_reviews,
        open_prs=open_prs,
        closed_prs=closed_prs,
    )


# ─── Reviews ─────────────────────────────────────────────────────────────────

@app.get("/api/reviews", response_model=List[ReviewListItem])
async def list_reviews(db: AsyncSession = Depends(get_db)):
    """
    Returns all reviewed PRs (status = completed) for the recent reviews table.
    """
    result = await db.execute(
        select(PullRequest)
        .where(PullRequest.status == "completed")
        .order_by(PullRequest.created_at.desc())
        .limit(50)
    )
    prs = result.scalars().all()

    return [
        ReviewListItem(
            id=str(pr.id),
            repository=pr.repo_full_name,
            pr_number=pr.pr_number,
            status=pr.status,
            created_at=pr.created_at.strftime("%Y-%m-%d") if pr.created_at else None,
        )
        for pr in prs
    ]


@app.get("/api/reviews/{review_id}", response_model=ReviewDetail)
async def get_review(review_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Returns full review detail including findings for the Review Details page.
    """
    pr_result = await db.execute(
        select(PullRequest).where(PullRequest.id == review_id)
    )
    pr = pr_result.scalar_one_or_none()

    if not pr:
        raise HTTPException(status_code=404, detail="Review not found")

    findings_result = await db.execute(
        select(Finding).where(Finding.pr_id == review_id)
    )
    findings = findings_result.scalars().all()

    # Split findings into messages and recommendations by severity
    finding_messages = [
        f"[{f.severity or 'info'}] {f.file or ''}{'#L' + str(f.line) if f.line else ''}: {f.message or ''}"
        for f in findings
        if f.message
    ]

    recommendations = list({
        f"Fix {f.severity} issue in {f.file or 'codebase'}"
        for f in findings
        if f.severity in ("high", "medium")
    })

    # Simple score: 10 minus high/medium finding count (floor 0)
    high_count = sum(1 for f in findings if f.severity == "high")
    medium_count = sum(1 for f in findings if f.severity == "medium")
    score = max(0, 10 - high_count * 2 - medium_count)

    # Build GitHub PR URL
    github_url = (
        f"https://github.com/{pr.repo_full_name}/pull/{pr.pr_number}"
        if pr.repo_full_name and pr.pr_number
        else None
    )

    return ReviewDetail(
        id=str(pr.id),
        repository=pr.repo_full_name,
        pr_number=pr.pr_number,
        pr_title=f"PR #{pr.pr_number}",
        review_date=pr.created_at.strftime("%Y-%m-%d") if pr.created_at else None,
        summary=(
            f"AI review completed for PR #{pr.pr_number} in {pr.repo_full_name}. "
            f"Found {len(findings)} issue(s): "
            f"{high_count} high, {medium_count} medium severity."
        ) if findings else f"Review completed for PR #{pr.pr_number}. No issues found.",
        findings=finding_messages,
        recommendations=recommendations,
        score=score,
        github_url=github_url,
    )
