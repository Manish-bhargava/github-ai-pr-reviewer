# schemas.py  —  Gateway Service
# Pydantic response shapes returned to the frontend

from typing import List, Optional
from pydantic import BaseModel


class DashboardStats(BaseModel):
    repositories: int
    prs_reviewed: int
    reviews_generated: int
    open_prs: int


class RepositoryInfo(BaseModel):
    id: int
    name: str
    status: str
    last_review: Optional[str] = None


class RepositoryDetail(BaseModel):
    id: int
    name: str
    total_reviews: int
    open_prs: int
    closed_prs: int


class PRItem(BaseModel):
    number: int
    title: str
    status: str
    created_at: Optional[str] = None


class ReviewListItem(BaseModel):
    id: str
    repository: str
    pr_number: int
    status: str
    created_at: Optional[str] = None


class ReviewDetail(BaseModel):
    id: str
    repository: str
    pr_number: int
    pr_title: Optional[str] = None
    review_date: Optional[str] = None
    summary: Optional[str] = None
    findings: List[str] = []
    recommendations: List[str] = []
    score: int = 0
    github_url: Optional[str] = None


class GitHubInstallUrl(BaseModel):
    url: str
