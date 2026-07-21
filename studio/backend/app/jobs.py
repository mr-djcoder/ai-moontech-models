import uuid

from app.schema import Candidate, JobStatus


class JobStore:
    def __init__(self):
        self._jobs: dict[str, JobStatus] = {}

    def create(self) -> str:
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = JobStatus(status="running", candidates=[])
        return job_id

    def set_result(self, job_id: str, candidates: list[Candidate]) -> None:
        self._jobs[job_id] = JobStatus(status="done", candidates=candidates)

    def set_error(self, job_id: str, message: str) -> None:
        self._jobs[job_id] = JobStatus(status="error", candidates=[], error=message)

    def get(self, job_id: str) -> JobStatus:
        return self._jobs[job_id]
