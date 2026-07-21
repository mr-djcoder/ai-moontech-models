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


def test_get_models_empty(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)
    resp = client.get("/models")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_models_and_get_one(tmp_path, monkeypatch):
    from app import main, models_store
    from app.schema import Attributes, Card

    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)
    card = Card(
        slug="jess", name="Jess", gender="female", status="card",
        identity_string="s", seed=48120, attributes=Attributes(age_band="late 20s"),
        reference_images=["reference/front.png"], provenance="synthetic",
        release=None, created="2026-07-21",
    )
    models_store.write_card(tmp_path, card)

    list_resp = client.get("/models")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["slug"] == "jess"

    get_resp = client.get("/models/jess")
    assert get_resp.status_code == 200
    assert get_resp.json()["seed"] == 48120

    missing_resp = client.get("/models/nope")
    assert missing_resp.status_code == 404


def test_generate_sheet_uses_card_identity_and_seed(tmp_path, monkeypatch):
    from app import main, models_store
    from app.schema import Attributes, Card

    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)
    card = Card(
        slug="jess", name="Jess", gender="female", status="card",
        identity_string="a synthetic woman, late 20s", seed=48120,
        attributes=Attributes(age_band="late 20s"), reference_images=[],
        provenance="synthetic", release=None, created="2026-07-21",
    )
    models_store.write_card(tmp_path, card)

    def fake_free_vram(**kwargs):
        return {"stopped": True}
    def fake_restore_model(**kwargs):
        return {"restored": True}
    def fake_submit(graph, **kwargs):
        assert graph["8"]["inputs"]["seed"] == 48120
        return "prompt-x"
    def fake_poll_history(prompt_id, **kwargs):
        return {"status": {"status_str": "success"},
                "outputs": {"11": {"images": [{"filename": "f.png", "subfolder": "j", "type": "output"}]}}}

    monkeypatch.setattr(main.vram, "free_vram", fake_free_vram)
    monkeypatch.setattr(main.vram, "restore_model", fake_restore_model)
    monkeypatch.setattr(main.comfy, "submit", fake_submit)
    monkeypatch.setattr(main.comfy, "poll_history", fake_poll_history)

    resp = client.post("/generate-sheet", json={"slug": "jess"})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    status = client.get(f"/jobs/{job_id}").json()
    assert status["status"] == "done"


def test_generate_sheet_unknown_slug_404(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)
    resp = client.post("/generate-sheet", json={"slug": "nope"})
    assert resp.status_code == 404


def test_post_models_rejects_minor(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)
    resp = client.post("/models", json={
        "slug": "x", "name": "X", "gender": "female",
        "identity_string": "s", "seed": 1,
        "attributes": {"age_band": "teen"},
        "provenance": "synthetic", "release": None,
        "picked": {"front": "f.png", "34": "t.png", "profile": "p.png", "body": "b.png"},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "adult" in body["reason"].lower()
    assert not (tmp_path / "x" / "card.json").exists()


def test_post_models_saves_and_commits(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)

    job_dir = tmp_path.parent / "job_output"
    job_dir.mkdir()
    for name in ["f.png", "t.png", "p.png", "b.png"]:
        (job_dir / name).write_bytes(b"fake")

    def fake_source_dir_for(slug):
        return job_dir
    monkeypatch.setattr(main, "_candidate_source_dir", fake_source_dir_for)

    def fake_commit_and_push(repo_root, add_path, message, **kwargs):
        return "abc1234"
    monkeypatch.setattr(main.git_ops, "commit_and_push", fake_commit_and_push)

    resp = client.post("/models", json={
        "slug": "jess", "name": "Jess", "gender": "female",
        "identity_string": "a synthetic woman, late 20s", "seed": 48120,
        "attributes": {"age_band": "late 20s"},
        "provenance": "synthetic", "release": None,
        "picked": {"front": "f.png", "34": "t.png", "profile": "p.png", "body": "b.png"},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["commit"] == "abc1234"
    assert (tmp_path / "jess" / "card.json").exists()
    assert (tmp_path / "jess" / "reference" / "front.png").exists()


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


def test_dedup_check_stub_returns_no_matches():
    resp = client.post("/dedup-check", json={"attributes": {"age_band": "late 20s"}})
    assert resp.status_code == 200
    assert resp.json() == {"matches": []}
