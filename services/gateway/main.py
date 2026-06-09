import hashlib
import hmac
import logging

import httpx
from fastapi import FastAPI, HTTPException, Request

from models import Settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

settings = Settings()

app = FastAPI(title="Gateway Service")


@app.get("/")
async def root():
    return {
        "service": "gateway",
        "status": "running",
        "endpoints": {
            "health": "GET /health",
            "github_webhook": "POST /webhook/github",
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway"}


@app.post("/webhook/github")
async def github_webhook(request: Request):
    body = await request.body()
    signature_header = request.headers.get("X-Hub-Signature-256", "")

    if not settings.github_webhook_secret:
        logger.warning("GITHUB_WEBHOOK_SECRET is not set; rejecting webhook")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    secret = settings.github_webhook_secret.encode()
    generated_signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    expected = "sha256=" + generated_signature

    if not hmac.compare_digest(expected, signature_header):
        logger.warning("Invalid GitHub webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.webhook_service_url}/events",
            content=body,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()

    logger.info("Forwarded GitHub webhook to webhook service")
    return {"status": "ok"}
import hashlib
import hmac
import logging

import httpx
from fastapi import FastAPI, HTTPException, Request

from models import Settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

settings = Settings()

app = FastAPI(title="Gateway Service")


@app.get("/")
async def root():
    return {
        "service": "gateway",
        "status": "running",
        "endpoints": {
            "health": "GET /health",
            "github_webhook": "POST /webhook/github",
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway"}


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

    return {"status": "ok"}