import json
import time
import urllib.parse
import urllib.request

from app.config import COMFYUI_URL


def _http_get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())


def _http_post(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def submit(graph: dict, http_post=_http_post) -> str:
    resp = http_post(f"{COMFYUI_URL}/prompt", {"prompt": graph})
    return resp["prompt_id"]


def poll_history(
    prompt_id: str,
    http_get=_http_get,
    max_attempts: int = 60,
    delay: float = 1.0,
    sleep=time.sleep,
) -> dict:
    for _ in range(max_attempts):
        history = http_get(f"{COMFYUI_URL}/history/{prompt_id}")
        entry = history.get(prompt_id)
        if entry and entry.get("status", {}).get("status_str") in ("success", "error"):
            return entry
        sleep(delay)
    raise TimeoutError(f"ComfyUI job {prompt_id} did not finish in time")


def output_image_url(filename: str, subfolder: str = "", folder_type: str = "output") -> str:
    params = urllib.parse.urlencode({
        "filename": filename, "subfolder": subfolder, "type": folder_type,
    })
    return f"{COMFYUI_URL}/view?{params}"
