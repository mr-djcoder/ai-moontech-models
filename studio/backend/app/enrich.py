import json
import re
import urllib.request

from app.config import OLLAMA_URL, CODING_MODEL

# The local LLM expands a sparse brief into a detailed, physically-grounded
# photoreal prompt. The whole point is to defeat the "obviously AI" look: the
# instruction forces real skin texture, real hair (the #1 giveaway), asymmetry,
# and candid lighting rather than the smooth, symmetric, studio-perfect default.
_INSTRUCTION = (
    "Expand this short description of a FICTIONAL synthetic person into ONE detailed "
    "photorealistic image prompt. Ground every detail in physical reality: individual "
    "skin texture with visible pores, faint blemishes and uneven skin tone; realistic "
    "hair with individual strands, flyaways, a natural imperfect hairline and visible "
    "roots; subtle facial asymmetry; natural under-eye shadows and fine lines; candid, "
    "non-studio available lighting; captured on a real camera with a portrait lens and "
    "shallow depth of field. Preserve every attribute in the description. Output ONLY "
    "the prompt as one paragraph, no preamble, no quotes, no markdown, no lists."
)

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _http_post(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def _clean(text: str) -> str:
    text = _THINK.sub("", text)
    text = text.strip().strip('"').strip("`").strip()
    return " ".join(text.split())


def enrich_identity(identity_string: str, http_post=_http_post, model: str = CODING_MODEL) -> str:
    """Expand a sparse identity string into a detailed photoreal prompt via the local
    LLM. Never blocks generation: on any failure, empty result, or missing Ollama, it
    returns the input unchanged so a shoot always proceeds."""
    prompt = f"{_INSTRUCTION}\n\nDescription: {identity_string}\n\nPrompt:"
    try:
        resp = http_post(
            f"{OLLAMA_URL}/api/generate",
            {"model": model, "prompt": prompt, "stream": False,
             "options": {"temperature": 0.7, "num_predict": 220}},
        )
    except Exception:  # noqa: BLE001 - enrichment is best-effort, never fatal
        return identity_string
    return _clean(resp.get("response") or "") or identity_string
