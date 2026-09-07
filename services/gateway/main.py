
# main.py — Gateway Service
# Handles:
#   - GitHub webhook forwarding
#   - GitHub App installation URL

import hashlib
import hmac
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from models import Settings


# ─── Logging ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


# ─── Settings ───────────────────────────────────────────────────────────────

settings = Settings()


# ─── Lifespan ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Gateway Service starting")

    yield

    logger.info("🛑 Gateway Service stopped")


# ─── App ────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Gateway Service",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health / Root ──────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "service": "gateway",
        "status": "running",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "gateway",
    }


# ─── GitHub Webhook ─────────────────────────────────────────────────────────

@app.post("/webhook/github")
async def github_webhook(request: Request):
    body = await request.body()

    signature_header = request.headers.get(
        "X-Hub-Signature-256",
        "",
    )

    if not settings.github_webhook_secret:
        logger.error("GITHUB_WEBHOOK_SECRET not configured")
        raise HTTPException(
            status_code=500,
            detail="Webhook secret not configured",
        )

    # Verify GitHub webhook signature
    secret = settings.github_webhook_secret.encode()

    generated_signature = hmac.new(
        secret,
        body,
        hashlib.sha256,
    ).hexdigest()

    expected_signature = f"sha256={generated_signature}"

    if not hmac.compare_digest(
        expected_signature,
        signature_header,
    ):
        logger.warning("Invalid GitHub webhook signature")
        raise HTTPException(
            status_code=401,
            detail="Invalid signature",
        )

    # Forward webhook to webhook service
    webhook_url = f"{settings.webhook_service_url}/events"

    logger.info(
        "Forwarding GitHub webhook to %s",
        webhook_url,
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": request.headers.get(
                        "X-GitHub-Event",
                        "",
                    ),
                },
                timeout=30,
            )

            response.raise_for_status()

    except Exception as e:
        logger.exception("Failed to forward webhook")

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )

    logger.info("GitHub webhook forwarded successfully")

    return {
        "status": "ok",
    }


# ─── GitHub App Installation / OAuth ────────────────────────────────────────

@app.get("/api/github/install-url")
async def get_install_url():
    """
    Returns the GitHub App installation URL.
    Used by the frontend GitHub Connect button.
    """

    if not settings.github_app_name:
        raise HTTPException(
            status_code=500,
            detail="GITHUB_APP_NAME not configured",
        )

    url = (
        f"https://github.com/apps/"
        f"{settings.github_app_name}/installations/new"
    )

    return {
        "url": url,
    }

