from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


from unittest.mock import patch


def test_generate_describe_and_poll_job(monkeypatch):
    from app import main

    def fake_free_vram(**kwargs):
        return {"model": "qwen3-coder-32k", "stopped": True}

    def fake_restore_model(**kwargs):
        return {"model": "qwen3-coder-32k", "restored": True}

    def fake_submit(graph, **kwargs):
        return "prompt-front"

    def fake_poll_history(prompt_id, **kwargs):
        return {"status": {"status_str": "success"},
                "outputs": {"11": {"images": [{"filename": "front_0.png", "subfolder": "job1", "type": "output"}]}}}

    monkeypatch.setattr(main.vram, "free_vram", fake_free_vram)
    monkeypatch.setattr(main.vram, "restore_model", fake_restore_model)
    monkeypatch.setattr(main.comfy, "submit", fake_submit)
    monkeypatch.setattr(main.comfy, "poll_history", fake_poll_history)

    resp = client.post("/generate", json={
        "mode": "describe",
        "attributes": {"age_band": "late 20s"},
        "identity_string": "a synthetic woman, late 20s",
        "seed": 48120,
        "count": 1,
    })
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    status_resp = client.get(f"/jobs/{job_id}")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "done"
    assert len(body["candidates"]) == 4  # one per angle
    assert {c["angle"] for c in body["candidates"]} == {"front", "34", "profile", "body"}


def test_jobs_unknown_id_returns_404():
    resp = client.get("/jobs/does-not-exist")
    assert resp.status_code == 404


def test_generate_restores_vram_even_when_comfy_job_errors(monkeypatch):
    from app import main

    restore_calls = []

    def fake_free_vram(**kwargs):
        return {"model": "qwen3-coder-32k", "stopped": True}

    def fake_restore_model(**kwargs):
        restore_calls.append(True)
        return {"model": "qwen3-coder-32k", "restored": True}

    def fake_submit(graph, **kwargs):
        return "prompt-front"

    def fake_poll_history(prompt_id, **kwargs):
        # Simulate ComfyUI reporting a failed job for the first angle.
        return {"status": {"status_str": "error"}, "outputs": {}}

    monkeypatch.setattr(main.vram, "free_vram", fake_free_vram)
    monkeypatch.setattr(main.vram, "restore_model", fake_restore_model)
    monkeypatch.setattr(main.comfy, "submit", fake_submit)
    monkeypatch.setattr(main.comfy, "poll_history", fake_poll_history)

    resp = client.post("/generate", json={
        "mode": "describe",
        "attributes": {"age_band": "late 20s"},
        "identity_string": "a synthetic woman, late 20s",
        "seed": 48120,
        "count": 1,
    })
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    status_resp = client.get(f"/jobs/{job_id}")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "error"
    assert restore_calls == [True]


def test_generate_restores_vram_on_unexpected_exception(monkeypatch):
    from app import main

    restore_calls = []

    def fake_free_vram(**kwargs):
        return {"model": "qwen3-coder-32k", "stopped": True}

    def fake_restore_model(**kwargs):
        restore_calls.append(True)
        return {"model": "qwen3-coder-32k", "restored": True}

    def fake_submit(graph, **kwargs):
        raise RuntimeError("comfyui connection refused")

    def fake_poll_history(prompt_id, **kwargs):
        raise AssertionError("poll_history should not be reached if submit raises")

    monkeypatch.setattr(main.vram, "free_vram", fake_free_vram)
    monkeypatch.setattr(main.vram, "restore_model", fake_restore_model)
    monkeypatch.setattr(main.comfy, "submit", fake_submit)
    monkeypatch.setattr(main.comfy, "poll_history", fake_poll_history)

    resp = client.post("/generate", json={
        "mode": "describe",
        "attributes": {"age_band": "late 20s"},
        "identity_string": "a synthetic woman, late 20s",
        "seed": 48120,
        "count": 1,
    })
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    status_resp = client.get(f"/jobs/{job_id}")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "error"
    assert restore_calls == [True]
