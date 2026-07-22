import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _wait_job(job_id, timeout=5.0):
    # Generation now runs on a background thread, so the POST returns before the
    # job finishes. Poll the same way the real frontend does.
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/jobs/{job_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


@pytest.fixture(autouse=True)
def _no_ollama_enrich(monkeypatch):
    # Enrichment calls the local LLM; keep the API tests hermetic by making it a
    # passthrough so /generate paths never touch Ollama. enrich itself is unit-tested
    # separately in test_enrich.py.
    from app import main
    monkeypatch.setattr(main.enrich, "enrich_identity", lambda s, **k: s)


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

    body = _wait_job(job_id)
    assert body["status"] == "done"
    assert len(body["candidates"]) == 4  # one per angle
    assert {c["angle"] for c in body["candidates"]} == {"front", "34", "profile", "body"}
    # Candidates round-trip the exact filename + subfolder from ComfyUI history,
    # so a client never has to parse them back out of the view URL.
    for c in body["candidates"]:
        assert c["filename"] == "front_0.png"
        assert c["subfolder"] == "job1"


def test_upload_reference_saves_and_returns_filename(monkeypatch, tmp_path):
    from app import main
    monkeypatch.setattr(main, "COMFYUI_INPUT_DIR", tmp_path)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    resp = client.post("/upload", files={"file": ("ref.png", png, "image/png")})
    assert resp.status_code == 200
    name = resp.json()["ref_image"]
    assert name.startswith("ref_") and name.endswith(".png")
    assert (tmp_path / name).read_bytes() == png


def test_upload_reference_rejects_non_image(monkeypatch, tmp_path):
    from app import main
    monkeypatch.setattr(main, "COMFYUI_INPUT_DIR", tmp_path)
    resp = client.post("/upload", files={"file": ("evil.txt", b"nope", "text/plain")})
    assert resp.status_code == 400


def test_jobs_unknown_id_returns_404():
    resp = client.get("/jobs/does-not-exist")
    assert resp.status_code == 404


def test_generation_rejected_while_another_running():
    # Only one generation may run at a time (single ComfyUI / GPU). With the lock
    # already held, a new job is rejected via its error status instead of racing.
    from app import main
    from app.schema import GenerateRequest

    assert main._generation_lock.acquire(blocking=False)
    try:
        job_id = main.job_store.create()
        main._run_generate_job(
            job_id, GenerateRequest(mode="describe", identity_string="x", seed=1, count=1)
        )
        body = main.job_store.get(job_id)
        assert body.status == "error"
        assert "already running" in body.error
    finally:
        main._generation_lock.release()


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

    body = _wait_job(job_id)
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
        slug="kiana", name="Kiana", gender="female", status="card",
        identity_string="s", seed=48120, attributes=Attributes(age_band="late 20s"),
        reference_images=["reference/front.png"], provenance="synthetic",
        release=None, created="2026-07-21",
    )
    models_store.write_card(tmp_path, card)

    list_resp = client.get("/models")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["slug"] == "kiana"

    get_resp = client.get("/models/kiana")
    assert get_resp.status_code == 200
    assert get_resp.json()["seed"] == 48120

    missing_resp = client.get("/models/nope")
    assert missing_resp.status_code == 404


def test_generate_sheet_uses_card_identity_and_seed(tmp_path, monkeypatch):
    from app import main, models_store
    from app.schema import Attributes, Card

    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)
    card = Card(
        slug="kiana", name="Kiana", gender="female", status="card",
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

    resp = client.post("/generate-sheet", json={"slug": "kiana"})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    status = _wait_job(job_id)
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
        "picked": {"front": {"filename": "f.png"}, "34": {"filename": "t.png"},
                   "profile": {"filename": "p.png"}, "body": {"filename": "b.png"}},
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
        return "abc1234", None
    monkeypatch.setattr(main.git_ops, "commit_and_push", fake_commit_and_push)

    resp = client.post("/models", json={
        "slug": "kiana", "name": "Kiana", "gender": "female",
        "identity_string": "a synthetic woman, late 20s", "seed": 48120,
        "attributes": {"age_band": "late 20s"},
        "provenance": "synthetic", "release": None,
        "picked": {"front": {"filename": "f.png"}, "34": {"filename": "t.png"},
                   "profile": {"filename": "p.png"}, "body": {"filename": "b.png"}},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["commit"] == "abc1234"
    assert (tmp_path / "kiana" / "card.json").exists()
    assert (tmp_path / "kiana" / "reference" / "front.png").exists()


def test_post_models_rolls_back_partial_write_on_bad_picked(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)

    job_dir = tmp_path.parent / "job_output_partial"
    job_dir.mkdir()
    # Only three of the four picked files exist; "body" names a missing file.
    for name in ["f.png", "t.png", "p.png"]:
        (job_dir / name).write_bytes(b"fake")

    def fake_source_dir_for(slug):
        return job_dir
    monkeypatch.setattr(main, "_candidate_source_dir", fake_source_dir_for)

    def fail_commit(*args, **kwargs):
        raise AssertionError("commit_and_push must not run when the write phase fails")
    monkeypatch.setattr(main.git_ops, "commit_and_push", fail_commit)

    resp = client.post("/models", json={
        "slug": "kiana", "name": "Kiana", "gender": "female",
        "identity_string": "a synthetic woman, late 20s", "seed": 48120,
        "attributes": {"age_band": "late 20s"},
        "provenance": "synthetic", "release": None,
        "picked": {"front": {"filename": "f.png"}, "34": {"filename": "t.png"},
                   "profile": {"filename": "p.png"}, "body": {"filename": "missing.png"}},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["reason"]
    # A failed save must leave zero trace: no partial models/<slug>/ folder.
    assert not (tmp_path / "kiana").exists()


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

    body = _wait_job(job_id)
    assert body["status"] == "error"
    assert restore_calls == [True]


def test_dedup_check_stub_returns_no_matches():
    resp = client.post("/dedup-check", json={"attributes": {"age_band": "late 20s"}})
    assert resp.status_code == 200
    assert resp.json() == {"matches": []}


def test_cors_allows_dev_origin():
    resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_serves_existing_reference_image(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)
    ref = tmp_path / "kiana" / "reference"
    ref.mkdir(parents=True)
    (ref / "front.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 2000)

    resp = client.get("/models/kiana/reference/front.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert len(resp.content) > 1000


def test_missing_reference_image_404():
    resp = client.get("/models/kiana/reference/does-not-exist.png")
    assert resp.status_code == 404


def test_reference_image_rejects_traversal():
    resp = client.get("/models/kiana/reference/..%2f..%2fcard.json")
    assert resp.status_code == 404


def test_reference_image_dotdot_filename_exercises_guard():
    # A literal ".." segment is normalized away by httpx's URL handling before
    # the request is even sent (it never reaches the ASGI app), so it can't be
    # used to prove the guard runs. Percent-encoding the dots (%2e%2e) survives
    # client-side normalization and is decoded back to ".." by the time it
    # reaches the route, so it actually exercises the handler's guard.
    resp = client.get("/models/kiana/reference/%2e%2e")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "reference image not found"


def test_reference_image_rejects_traversal_slug():
    resp = client.get("/models/..%2freference/front.png")
    assert resp.status_code == 404


def test_comfy_image_proxies_bytes(monkeypatch):
    from app import main

    def fake_fetch(filename, subfolder, folder_type):
        assert filename == "sheet_front_0.png"
        assert folder_type == "output"
        return b"\x89PNG\r\nDATA", "image/png"
    monkeypatch.setattr(main.comfy, "fetch_output_image", fake_fetch)

    resp = client.get("/comfy-image?filename=sheet_front_0.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content == b"\x89PNG\r\nDATA"


def test_comfy_image_rejects_bad_filename():
    resp = client.get("/comfy-image?filename=..%2f..%2fetc")
    assert resp.status_code == 404


def test_comfy_image_upstream_failure_502(monkeypatch):
    from app import main

    def boom(*a, **k):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(main.comfy, "fetch_output_image", boom)

    resp = client.get("/comfy-image?filename=x.png")
    assert resp.status_code == 502


def test_delete_model_removes_folder(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)
    d = tmp_path / "kiana" / "reference"
    d.mkdir(parents=True)
    (tmp_path / "kiana" / "card.json").write_text("{}")
    (d / "front.png").write_bytes(b"x")

    resp = client.delete("/models/kiana")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert not (tmp_path / "kiana").exists()


def test_delete_missing_model_404(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)
    resp = client.delete("/models/ghost")
    assert resp.status_code == 404


def test_delete_rejects_traversal_slug(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)
    # Percent-encoded traversal survives client normalization and reaches the
    # handler, which must reject it without touching anything outside the root.
    resp = client.delete("/models/..%2f..%2fmodels")
    assert resp.status_code == 404
    assert tmp_path.exists()


def test_dataset_endpoint_runs_job_and_returns_candidates(monkeypatch, tmp_path):
    from app import main, models_store
    from app.schema import Attributes, Card

    # A saved card on disk with one reference frame.
    card = Card(
        slug="cecil", name="Cecil", gender="Female", status="card",
        identity_string="a Filipino woman, mid 40s", seed=123,
        attributes=Attributes(age_band="mid 40s"),
        reference_images=["reference/front.png"], provenance="synthetic",
        created="2026-07-22",
    )
    monkeypatch.setattr(main.models_store, "read_card", lambda root, slug: card)
    # Reference frame source file exists so the copy-into-input step succeeds.
    ref_src = tmp_path / "cecil" / "reference"
    ref_src.mkdir(parents=True)
    (ref_src / "front.png").write_bytes(b"png")
    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)
    monkeypatch.setattr(main, "COMFYUI_INPUT_DIR", tmp_path / "input")

    monkeypatch.setattr(main.vram, "free_vram", lambda: None)
    monkeypatch.setattr(main.vram, "restore_model", lambda: None)
    monkeypatch.setattr(main.comfy, "submit", lambda graph: "pid")

    def fake_poll(prompt_id, **kw):
        return {"status": {"status_str": "success"},
                "outputs": {"11": {"images": [
                    {"filename": "sheet_ref_front_0.png", "subfolder": "job"}]}}}
    monkeypatch.setattr(main.comfy, "poll_history", fake_poll)

    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    r = client.post("/models/cecil/dataset", json={"count": 4})
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    # Job runs on a background thread; poll to completion.
    import time
    for _ in range(50):
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.02)
    assert job["status"] == "done"
    assert len(job["candidates"]) == 4
    assert job["candidates"][0]["filename"] == "sheet_ref_front_0.png"


def test_dataset_endpoint_unknown_slug_returns_404(monkeypatch, tmp_path):
    from app import main

    def _raise_not_found(root, slug):
        raise FileNotFoundError(slug)
    monkeypatch.setattr(main.models_store, "read_card", _raise_not_found)
    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)

    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    r = client.post("/models/does-not-exist/dataset", json={"count": 4})
    assert r.status_code == 404


def test_dataset_endpoint_empty_reference_images_returns_400(monkeypatch, tmp_path):
    from app import main
    from app.schema import Attributes, Card

    card = Card(
        slug="cecil", name="Cecil", gender="Female", status="card",
        identity_string="a Filipino woman, mid 40s", seed=123,
        attributes=Attributes(age_band="mid 40s"),
        reference_images=[], provenance="synthetic",
        created="2026-07-22",
    )
    monkeypatch.setattr(main.models_store, "read_card", lambda root, slug: card)
    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)

    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    r = client.post("/models/cecil/dataset", json={"count": 4})
    assert r.status_code == 400


def test_dataset_endpoint_missing_reference_file_returns_400(monkeypatch, tmp_path):
    from app import main
    from app.schema import Attributes, Card

    # Card lists a reference frame, but it was never written to disk.
    card = Card(
        slug="cecil", name="Cecil", gender="Female", status="card",
        identity_string="a Filipino woman, mid 40s", seed=123,
        attributes=Attributes(age_band="mid 40s"),
        reference_images=["reference/front.png"], provenance="synthetic",
        created="2026-07-22",
    )
    monkeypatch.setattr(main.models_store, "read_card", lambda root, slug: card)
    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)

    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    r = client.post("/models/cecil/dataset", json={"count": 4})
    assert r.status_code == 400


def test_dataset_endpoint_non_numeric_count_returns_400(monkeypatch, tmp_path):
    from app import main
    from app.schema import Attributes, Card

    card = Card(
        slug="cecil", name="Cecil", gender="Female", status="card",
        identity_string="a Filipino woman, mid 40s", seed=123,
        attributes=Attributes(age_band="mid 40s"),
        reference_images=["reference/front.png"], provenance="synthetic",
        created="2026-07-22",
    )
    monkeypatch.setattr(main.models_store, "read_card", lambda root, slug: card)
    ref_src = tmp_path / "cecil" / "reference"
    ref_src.mkdir(parents=True)
    (ref_src / "front.png").write_bytes(b"png")
    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)
    monkeypatch.setattr(main, "COMFYUI_INPUT_DIR", tmp_path / "input")

    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    r = client.post("/models/cecil/dataset", json={"count": "abc"})
    assert r.status_code == 400
