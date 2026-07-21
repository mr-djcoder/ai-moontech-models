# ai-moontech-models

A public, reusable collection of synthetic actors ("talent") for AI-generated
video/ads, plus the Studio app used to create and browse them.

- `models/<slug>/` — one card per talent (card.json, card.md, reference/ sheet)
- `studio/backend/` — FastAPI app that orchestrates ComfyUI to generate cards
- `studio/frontend/` — (not yet built) React/Vite UI

See `studio/backend/README.md` to run the backend.
