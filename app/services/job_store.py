import secrets
import time
from dataclasses import dataclass
from threading import Lock
from typing import Literal

JobStatus = Literal["queued", "processing", "done", "failed"]


@dataclass
class SummaryJob:
    job_id: str
    url: str
    status: JobStatus
    created_at: float
    updated_at: float
    result_text: str = ""
    error_text: str = ""


class JobStore:
    def __init__(self, max_jobs: int = 500, ttl_seconds: int = 3600) -> None:
        self.max_jobs = max_jobs
        self.ttl_seconds = ttl_seconds
        self._jobs: dict[str, SummaryJob] = {}
        self._lock = Lock()

    def create(self, url: str) -> SummaryJob:
        now = time.time()
        job_id = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:10]
        job = SummaryJob(
            job_id=job_id,
            url=url,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._prune(now)
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> SummaryJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def mark_processing(self, job_id: str) -> None:
        self._set_status(job_id, "processing")

    def mark_done(self, job_id: str, result_text: str) -> None:
        now = time.time()
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.status = "done"
            job.result_text = result_text
            job.error_text = ""
            job.updated_at = now

    def mark_failed(self, job_id: str, error_text: str) -> None:
        now = time.time()
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.status = "failed"
            job.error_text = error_text
            job.updated_at = now

    def _set_status(self, job_id: str, status: JobStatus) -> None:
        now = time.time()
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.status = status
            job.updated_at = now

    def _prune(self, now: float) -> None:
        expired_ids = [
            job_id
            for job_id, job in self._jobs.items()
            if now - job.created_at > self.ttl_seconds
        ]
        for job_id in expired_ids:
            self._jobs.pop(job_id, None)

        if len(self._jobs) <= self.max_jobs:
            return

        ordered = sorted(self._jobs.values(), key=lambda job: job.created_at)
        overflow = len(self._jobs) - self.max_jobs
        for job in ordered[:overflow]:
            self._jobs.pop(job.job_id, None)
