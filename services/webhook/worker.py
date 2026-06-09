import logging
import os

import httpx
from celery import Celery

logger = logging.getLogger(__name__)

redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
orchestrator_service_url = os.environ.get("ORCHESTRATOR_SERVICE_URL", "http://orchestrator:8002")
learner_service_url = os.environ.get("LEARNER_SERVICE_URL", "http://learner:8004")

app = Celery("webhook", broker=redis_url, backend=redis_url)
app.conf.task_routes = {
    "analyze_pr": {"queue": "webhook"},
    "trigger_learning": {"queue": "learning"},
}



@app.task(name="analyze_pr")
def analyze_pr(
    pr_id: str,
    pr_number: int,
    repo_full_name: str,
    head_sha: str,
    installation_id: int,
):
    logger.info("Analyzing PR %s/%s", repo_full_name, pr_number)
    with httpx.Client() as client:
        response = client.post(
            f"{orchestrator_service_url}/analyze",
            json={
                "pr_id": pr_id,
                "pr_number": pr_number,
                "repo_full_name": repo_full_name,
                "head_sha": head_sha,
                "installation_id": installation_id,
            },
            timeout=120,
        )
        response.raise_for_status()
    logger.info("Orchestrator accepted analysis for PR %s/%s", repo_full_name, pr_number)


@app.task(name="trigger_learning")
def trigger_learning(repo_full_name: str, pr_id: str):
    logger.info("Triggering learning for %s PR %s", repo_full_name, pr_id)
    with httpx.Client() as client:
        response = client.post(
            f"{learner_service_url}/learn",
            json={"repo_full_name": repo_full_name, "pr_id": pr_id},
            timeout=60,
        )
        response.raise_for_status()
    logger.info("Learning completed for %s PR %s", repo_full_name, pr_id)
