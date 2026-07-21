from app import vram


def test_loaded_models_parses_names():
    def fake_get(url):
        assert url.endswith("/api/ps")
        return {"models": [{"name": "qwen3-coder-32k"}, {"name": "other"}]}
    assert vram.loaded_models(http_get=fake_get) == ["qwen3-coder-32k", "other"]


def test_free_vram_success():
    calls = []
    def fake_run(cmd):
        calls.append(cmd)
        return 0
    result = vram.free_vram(run=fake_run)
    assert result == {"model": "qwen3-coder-32k", "stopped": True}
    assert calls == [["ollama", "stop", "qwen3-coder-32k"]]


def test_free_vram_missing_ollama():
    def fake_run(cmd):
        raise FileNotFoundError()
    result = vram.free_vram(run=fake_run)
    assert result == {"model": "qwen3-coder-32k", "stopped": False}


def test_restore_model_success():
    def fake_post(url, payload):
        assert url.endswith("/api/generate")
        assert payload["model"] == "qwen3-coder-32k"
        return {"done": True}
    result = vram.restore_model(http_post=fake_post)
    assert result == {"model": "qwen3-coder-32k", "restored": True}


def test_restore_model_error_response():
    def fake_post(url, payload):
        return {"error": "model not found"}
    result = vram.restore_model(http_post=fake_post)
    assert result == {"model": "qwen3-coder-32k", "restored": False}
