import pytest
from app.jobs import JobStore
from app.schema import Candidate


def test_create_returns_unique_ids():
    store = JobStore()
    a, b = store.create(), store.create()
    assert a != b


def test_new_job_is_running():
    store = JobStore()
    job_id = store.create()
    status = store.get(job_id)
    assert status.status == "running"
    assert status.candidates == []


def test_set_result_marks_done():
    store = JobStore()
    job_id = store.create()
    store.set_result(job_id, [Candidate(
        url="http://x/1.png", filename="1.png", angle="front", index=0)])
    status = store.get(job_id)
    assert status.status == "done"
    assert len(status.candidates) == 1


def test_set_error_marks_error():
    store = JobStore()
    job_id = store.create()
    store.set_error(job_id, "boom")
    status = store.get(job_id)
    assert status.status == "error"
    assert status.error == "boom"


def test_get_unknown_job_raises():
    store = JobStore()
    with pytest.raises(KeyError):
        store.get("nonexistent")
