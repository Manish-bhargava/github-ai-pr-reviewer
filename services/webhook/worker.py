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

client = QStash(
    qstash_url,
    qstash_token,
)


def analyze_pr(
    pr_id: str,
    pr_number: int,
    repo_full_name: str,
    head_sha: str,
    installation_id: int,
):
    logger.info(
        "Queueing analysis for %s/%s",
        repo_full_name,
        pr_number,
    )

    client.publish(
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
        "Analysis queued for %s/%s",
        repo_full_name,
        pr_number,
    )


def trigger_learning(
    repo_full_name: str,
    pr_id: str,
):
    logger.info(
        "Queueing learning for %s PR %s",
        repo_full_name,
        pr_id,
    )

    client.publish(
        url=f"{learner_service_url}/learn",
        body={
            "repo_full_name": repo_full_name,
            "pr_id": pr_id,
        },
    )

    logger.info(
        "Learning queued for %s PR %s",
        repo_full_name,
        pr_id,
    )