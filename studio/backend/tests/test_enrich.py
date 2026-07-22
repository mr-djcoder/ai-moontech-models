from app import enrich


def test_enrich_returns_expanded_prompt():
    captured = {}

    def fake_post(url, payload):
        captured["url"] = url
        captured["payload"] = payload
        return {"response": "a synthetic woman, late 20s, visible skin pores, "
                            "flyaway hairs, natural hairline, candid window light"}

    out = enrich.enrich_identity("a synthetic woman, late 20s", http_post=fake_post)
    assert "visible skin pores" in out
    assert "flyaway hairs" in out
    assert captured["url"].endswith("/api/generate")
    assert "a synthetic woman, late 20s" in captured["payload"]["prompt"]
    assert captured["payload"]["stream"] is False


def test_enrich_strips_think_blocks_and_quotes():
    def fake_post(url, payload):
        return {"response": "<think>let me reason</think>  \"detailed photoreal prompt\"  "}

    out = enrich.enrich_identity("x", http_post=fake_post)
    assert out == "detailed photoreal prompt"


def test_enrich_falls_back_to_input_on_error():
    def boom(url, payload):
        raise RuntimeError("ollama down")

    original = "a synthetic man, early 30s"
    assert enrich.enrich_identity(original, http_post=boom) == original


def test_enrich_falls_back_on_empty_response():
    def empty(url, payload):
        return {"response": "   "}

    original = "a synthetic man, early 30s"
    assert enrich.enrich_identity(original, http_post=empty) == original
