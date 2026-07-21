import pytest
from app import comfy


def test_submit_returns_prompt_id():
    def fake_post(url, payload):
        assert url.endswith("/prompt")
        assert payload["prompt"] == {"1": {}}
        return {"prompt_id": "abc123"}
    assert comfy.submit({"1": {}}, http_post=fake_post) == "abc123"


def test_poll_history_returns_on_success():
    calls = {"n": 0}
    def fake_get(url):
        calls["n"] += 1
        if calls["n"] < 3:
            return {}
        return {"abc123": {"status": {"status_str": "success"}, "outputs": {}}}
    result = comfy.poll_history("abc123", http_get=fake_get, delay=0, sleep=lambda s: None)
    assert result["status"]["status_str"] == "success"
    assert calls["n"] == 3


def test_poll_history_returns_on_error():
    def fake_get(url):
        return {"abc123": {"status": {"status_str": "error"}, "outputs": {}}}
    result = comfy.poll_history("abc123", http_get=fake_get, delay=0, sleep=lambda s: None)
    assert result["status"]["status_str"] == "error"


def test_poll_history_times_out():
    def fake_get(url):
        return {}
    with pytest.raises(TimeoutError):
        comfy.poll_history("abc123", http_get=fake_get, max_attempts=3, delay=0, sleep=lambda s: None)


def test_output_image_url():
    url = comfy.output_image_url("front_0.png", subfolder="job123")
    assert url.startswith("http://127.0.0.1:8188/view")
    assert "filename=front_0.png" in url
    assert "subfolder=job123" in url
