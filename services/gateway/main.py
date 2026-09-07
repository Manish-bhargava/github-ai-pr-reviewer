
import hashlib
import hmac
import logging

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


# ─── App ────────────────────────────────────────────────────────────────────

app = FastAPI(title="Gateway Service")


# ─── CORS ───────────────────────────────────────────────────────────────────

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
    # Get the raw webhook body
    body = await request.body()

    # Get GitHub's signature
    signature_header = request.headers.get(
        "X-Hub-Signature-256",
        "",
    )

    # Make sure webhook secret is configured
    if not settings.github_webhook_secret:
        logger.error("GITHUB_WEBHOOK_SECRET not configured")
        raise HTTPException(
            status_code=500,
            detail="Webhook secret not configured",
        )

    # Generate our own HMAC-SHA256 signature
    secret = settings.github_webhook_secret.encode()

    generated_signature = hmac.new(
        secret,
        body,
        hashlib.sha256,
    ).hexdigest()

    expected_signature = f"sha256={generated_signature}"

    # Compare our signature with GitHub's signature
    if not hmac.compare_digest(
        expected_signature,
        signature_header,
    ):
        logger.warning("Invalid GitHub webhook signature")

        raise HTTPException(
            status_code=401,
            detail="Invalid signature",
        )

    # Forward the verified webhook to the webhook service
    webhook_url = f"{settings.webhook_service_url}/events"

    logger.info(
        "Forwarding webhook to %s",
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


# ─── GitHub App Installation ────────────────────────────────────────────────

@app.get("/api/github/install-url")
async def get_install_url():
    """
    Returns the GitHub App installation URL.
    Used by the frontend Connect GitHub button.
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

