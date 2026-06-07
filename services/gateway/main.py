import hashlib
import hmac

import httpx
from fastapi import FastAPI, HTTPException, Request
from prometheus_fastapi_instrumentator import Instrumentator

from models import Settings

settings = Settings()

app = FastAPI()

Instrumentator().instrument(app).expose(app)


@app.get("/health")
async def health():
    return {"status": "ok"}

# Receives webhook events from GitHub and verifies their authenticity
# using HMAC-SHA256 signature validation with a shared secret.
# After successful verification, the event is forwarded to the internal
# webhook processing service for further handling.
@app.post("/webhook/github")
async def github_webhook(request: Request):

    body = await request.body()

    signature_header = request.headers.get(
        "X-Hub-Signature-256",
        ""
    )

    secret = settings.github_webhook_secret.encode()

    hmac_object = hmac.new(
        secret,
        body,
        hashlib.sha256
    )

    generated_signature = hmac_object.hexdigest()

    expected = "sha256=" + generated_signature

    if not hmac.compare_digest(
        expected,
        signature_header
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid signature"
        )

    async with httpx.AsyncClient() as client:

        response = await client.post(
            "http://webhook:8001/events",
            content=body,
            headers={
                "Content-Type": "application/json"
            },
        )

        response.raise_for_status()

    return {"status": "ok"}