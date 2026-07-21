from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent.parent
MODELS_ROOT = REPO_ROOT / "models"

COMFYUI_URL = "http://127.0.0.1:8188"
OLLAMA_URL = "http://localhost:11434"
CODING_MODEL = "qwen3-coder-32k"

WORKFLOWS_DIR = BACKEND_ROOT / "workflows"
