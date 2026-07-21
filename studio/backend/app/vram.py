import json
import subprocess
import urllib.request

from app.config import OLLAMA_URL, CODING_MODEL


def _http_get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())


def _http_post(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode())


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30).returncode


def loaded_models(http_get=_http_get) -> list[str]:
    data = http_get(f"{OLLAMA_URL}/api/ps")
    return [m["name"] for m in data.get("models", []) if m.get("name")]


def free_vram(model: str = CODING_MODEL, run=_run) -> dict:
    try:
        code = run(["ollama", "stop", model])
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {"model": model, "stopped": False}
    return {"model": model, "stopped": code == 0}


def restore_model(model: str = CODING_MODEL, http_post=_http_post) -> dict:
    resp = http_post(f"{OLLAMA_URL}/api/generate",
                      {"model": model, "prompt": "", "stream": False})
    return {"model": model, "restored": bool(resp) and "error" not in resp}
