# Studio backend

Localhost-only FastAPI service. No auth. Talks to a local ComfyUI at
`http://127.0.0.1:8188` and Ollama at `http://localhost:11434`.

## Setup

    cd studio/backend
    python -m venv .venv
    .venv/Scripts/activate   # Windows
    pip install -r requirements.txt

## Run

    uvicorn app.main:app --reload --port 8800

## Test

    pytest -v
