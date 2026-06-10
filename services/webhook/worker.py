import logging
import os

from qstash.client import QStash

logger = logging.getLogger(__name__)

orchestrator_service_url = os.environ.get(
    "ORCHESTRATOR_SERVICE_URL",
    "http://orchestrator:8002",
)

learner_service_url = os.environ.get(
    "LEARNER_SERVICE_URL",
    "http://learner:8004",
)

qstash_url = os.environ["QSTASH_URL"]
qstash_token = os.environ["QSTASH_TOKEN"]

# QStash Client
client = QStash(
    qstash_token,
    base_url=qstash_url,
)

logger.info("✅ QStash client initialized")


def analyze_pr(
    pr_id: str,
    pr_number: int,
    repo_full_name: str,
    head_sha: str,
    installation_id: int,
):
    logger.info(
        "🚀 Publishing analysis job for %s/%s",
        repo_full_name,
        pr_number,
    )

    try:
        response = client.message.publish_json(
            url=f"{orchestrator_service_url}/analyze",
            body={
                "pr_id": pr_id,
                "pr_number": pr_number,
                "repo_full_name": repo_full_name,
                "head_sha": head_sha,
                "installation_id": installation_id,
            },
        )

        logger.info(
            "✅ Analysis published to QStash: %s",
            response,
        )

        return response

    except Exception:
        logger.exception(
            "❌ Failed to publish analysis job for %s/%s",
            repo_full_name,
            pr_number,
        )
        raise


def trigger_learning(
    repo_full_name: str,
    pr_id: str,
):
    logger.info(
        "🚀 Publishing learning job for %s PR %s",
        repo_full_name,
        pr_id,
    )

    try:
        response = client.message.publish_json(
            url=f"{learner_service_url}/learn",
            body={
                "repo_full_name": repo_full_name,
                "pr_id": pr_id,
            },
        )

        logger.info(
            "✅ Learning published to QStash: %s",
            response,
        )

        return response

    except Exception:
        logger.exception(
            "❌ Failed to publish learning job for %s PR %s",
            repo_full_name,
            pr_id,
        )
        raise