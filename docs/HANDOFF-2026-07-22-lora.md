# HANDOFF — Casting Studio: face-match fix + LoRA identity-lock

Date: 2026-07-22. Branch: `feat/casting-studio-frontend` (PR #1 → `main`, GitHub `mr-djcoder/ai-moontech-models`). HEAD at handoff: `cefe794`.

Read this to resume on another machine/account with zero re-derivation. Pairs with:
- Design spec: `docs/superpowers/specs/2026-07-22-model-studio-lora-identity-lock.md`
- Phase A plan (DONE): `docs/superpowers/plans/2026-07-22-lora-phase-a-dataset.md`

---

## 1. What this branch delivers

1. **Reference face-match fix** (commit `081982c`). Reference-mode model sheets were drifting the face to a generic, older person. Root cause: the original `qwen_image_edit` model held identity only via weak text-conditioning while the sampler painted an empty canvas at full denoise, so the real reference likeness was never anchored. Fix:
   - Model → **Qwen-Image-Edit-2511** (`qwen_image_edit_2511_fp8mixed.safetensors`).
   - Encoder → **`TextEncodeQwenImageEditPlus`** (VAE-encodes the reference into `reference_latents` appended to conditioning = real identity lock; multi-image capable).
   - **FaceDetailer** refine pass (Impact Pack + `face_yolov8m.pt`, denoise 0.35) crops + sharpens the face.
   - Files: `studio/backend/workflows/qwen-sheet-edit.json`, `studio/backend/app/workflows.py` (`build_reference_graph`).
   - Verified live on a real selfie across all 4 angles (front/34/profile/body).

2. **LoRA identity-lock — design + Phase A** (the real goal: a per-model trained LoRA so identity survives arbitrary scene/wardrobe/pose/seed; the reference-only path cannot). Phase A = dataset generation + curation. Commits `d0f445a`..`cefe794`.

---

## 2. Environment / how to run (localhost only, no auth)

| Piece | Path / command |
|---|---|
| Studio repo | `C:/Working/ai-moontech-models` |
| Backend | `cd studio/backend && uvicorn app.main:app --reload --port 8800` |
| Frontend | `cd studio/frontend && npm run dev` (→ :5173) · build check: `npm run build` |
| Backend tests | system `python -m pytest` (from `studio/backend`) — **118 passing** |
| ComfyUI | `C:/Working/local-ai-workstation/comfyui` |
| ComfyUI venv python | `C:/Working/local-ai-workstation/comfyui/.venv/Scripts/python.exe` (Python 3.12) |
| ComfyUI launch | `./.venv/Scripts/python.exe -s main.py --listen 127.0.0.1 --port 8188 --output-directory ./output` (cold start ~80s) |
| Ollama (enrich) | `localhost:11434`, model `qwen3-coder-32k` |
| GPU | single ~34 GB card; one heavy op at a time via `app/vram.py` broker |

Config: `studio/backend/app/config.py` — `COMFYUI_URL=127.0.0.1:8188`, input/output dirs under `C:/Working/local-ai-workstation/comfyui/{input,output}`.

### CRITICAL — the other machine needs these installed (not in git)

The 2511 model, custom nodes, and detector were installed locally this session and do **not** travel with the repo. Redo on the new machine:

```bash
PY="C:/Working/local-ai-workstation/comfyui/.venv/Scripts/python.exe"

# 1) Qwen-Image-Edit-2511 (fp8) — 20.5 GB. NOTE: there is NO 2511 fp8_e4m3fn variant; fp8mixed IS the fp8 option.
#    URL: https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors
#    -> comfyui/models/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors
#    (download via the venv python's urllib — see gotcha #4; plain curl fails TLS here.)

# 2) Impact Pack + Subpack (FaceDetailer)
cd C:/Working/local-ai-workstation/comfyui/custom_nodes
git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Impact-Pack.git
git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Impact-Subpack.git
"$PY" -m pip install -r ComfyUI-Impact-Pack/requirements.txt
"$PY" -m pip install -r ComfyUI-Impact-Subpack/requirements.txt

# 3) Face detector for FaceDetailer -> comfyui/models/ultralytics/bbox/face_yolov8m.pt (52 MB)
#    URL: https://huggingface.co/Bingsu/adetailer/resolve/main/face_yolov8m.pt
```

Already present on the original box (verify on new box): text encoder `qwen_2.5_vl_7b_fp8_scaled.safetensors` (text_encoders), `qwen_image_vae.safetensors` (vae), and **`qwen_image_fp8_e4m3fn.safetensors`** (the Qwen-Image *base* — needed for LoRA training + txt2img consumption in Phase B/C).

Restart ComfyUI after installing custom nodes so `FaceDetailer` / `UltralyticsDetectorProvider` register (confirm via `/object_info`).

---

## 3. Gotchas learned this session

1. **Describe vs reference mode.** The console defaults to **Describe** = synthetic (invents a face from the text brief, ignores the photo). To match a reference photo you MUST click **"From reference"** and upload. Output filenames tell you which ran: `sheet_*` = describe, `sheet_ref_*` = reference.
2. **Backend caches the workflow at import.** After editing `workflows.py` / the JSON, restart uvicorn (or rely on `--reload` for `.py` edits) so the new graph is loaded.
3. **Console localStorage resume.** An unsaved sheet auto-restores on load; click **Discard** on the yellow banner to clear it — a plain refresh keeps it.
4. **Sandboxed shell has no network; curl fails TLS (exit 35).** Do downloads with the ComfyUI venv python's `urllib` (works) and, in this harness, with sandbox disabled. Two ComfyUI instances cannot share port 8188 / the GPU.
5. **pytest lives in the *system* python, not the ComfyUI venv.** Run backend tests with `python -m pytest`.
6. **Save button gating:** needs a **Name** (→ slug) AND one picked frame per all four angles. "Promote to LoRA" in `SavePanel.jsx` is a Phase-2 stub; the working Train entry is the new `/model/:slug/train` route.

---

## 4. LoRA feature — design decisions (locked)

Full detail in the spec. Key choices:
- **Trainer = ComfyUI-native `TrainLoraNode`** (`comfy_extras/nodes_train.py`) — NO musubi/external trainer. Training becomes a graph submitted via `comfy.submit` like generation, reusing the VRAM broker.
- **Base model = Qwen-Image** (`qwen_image_fp8_e4m3fn`), consumed via plain **txt2img + LoRA + trigger word** (full scene freedom). Reference-edit path stays as the `card` fallback.
- **Dataset** = auto-generate ~40 varied on-identity shots (2511 pipeline) → user curates ≥20.
- **Wardrobe stays swappable** via captioning discipline: dataset is wardrobe-neutral, every caption names the wardrobe (captioned attrs stay variable; the uncaptioned face bakes to the trigger). Clothing at gen time = prompt or garment-ref (`TextEncodeQwenImageEditPlus` image2).
- **Output = reusable content pack** (LoRA + trigger + workflow snippets `frame-plain`/`frame-dress` + sample sheet + `pack.md`), copied to `comfyui/models/loras/` and recorded in `card.json` (`status:"lora"`, `LoraInfo`).
- **Human validation gate**: after training, auto-render a test with the LoRA; status flips to `lora` only on approval.

---

## 5. Phase A — DONE (dataset gen + curation)

Built subagent-driven, TDD, per-task reviewed + final whole-branch review (verdict: ready to merge). Commits & files:

| Commit | What |
|---|---|
| `d0f445a` | `workflows.build_reference_graph(..., extra="")` — optional prompt modifier |
| `c431bc9` | `app/dataset.py` — `DatasetVariant` + `dataset_variants(base_seed, count=40)` (angle × lighting × distance matrix, deterministic, distinct seeds) |
| `15de4cb` | `dataset.build_dataset_graphs(ref_image, identity_string, base_seed, count)` → per-variant graphs anchored on the card's ref |
| `b90b50d` | `POST /models/{slug}/dataset` background job (`_seed_card_reference`, `_run_dataset_job`) reusing lock + VRAM broker |
| `4f7f55c` | endpoint hardening: 404 unknown slug, 400 bad count, +4 branch tests |
| `9a97585` | frontend `/model/:slug/train` (`Train.jsx`, `api.generateDataset`, route, `CandidateGrid` additive `selected` multi-select prop) |
| `cefe794` | consistency: committed `Console.jsx` reference call matching `api.generateReference(identity_string)` |

---

## 6. NEXT — Phase B (the blocker is a spike)

**Spike first (do before writing the Phase B plan):** open ComfyUI, drop a `TrainLoraNode`, and record its exact **list-input wiring** in an API graph — the node is `is_input_list=True` and takes a **list of `latents`** (dataset images VAE-encoded) + a **list of `positive` conditionings** (captions). Determine how those lists are constructed in JSON (batching / a loader node), plus `SaveLoRA` params and the VRAM behavior of the fp8 Qwen-Image base with `training_dtype: none`.

`TrainLoraNode` confirmed inputs (`comfy_extras/nodes_train.py:954`): `model`, `latents`(list), `positive`(list), `batch_size`, `grad_accumulation_steps`, `steps`(def 16), `learning_rate`(0.0005), `rank`(≤128, def 8), `optimizer`(AdamW), `loss_function`(MSE), `seed`, `training_dtype`(bf16/fp32/none). `SaveLoRA` (`:1363`) writes to `models/loras/` (default `loras/ComfyUI_trained_lora`). `LossGraphNode` for loss curve. Starting hyperparams: rank 16–32, ~2000 steps, lr ~1e-4, batch 1, `training_dtype: none` on the fp8 base to fit ~34 GB (tune `grad_accumulation_steps`/rank if tight).

**Phase B deliverables:** `captions.py`, `train_graph.py`, `train_jobs.py` (phases generating→curating→training→validating→publishing), `pack.py`, `workflows/qwen-lora-train.json`, `POST /models/{slug}/train` + `/promote`, validation gate.

**Phase C:** `workflows/qwen-txt2img-lora.json`, status-branched generation dispatch (`lora` → txt2img+LoRA+trigger; `card` → reference-edit), `ai-moontech-media-studio` skill branch on status, roster/detail LoRA display.

**Deferred minors** (fold into Phase B's reference-seeding helper):
- `_run_dataset_job`: `free_vram()`/`read_card` sit outside the inner try → a job can stick in `running` on broker failure (mirrors pre-existing `_run_generate_job`; not a regression). Widen the try or wrap so any exception calls `job_store.set_error`.
- `_seed_card_reference`: orphaned `ds_<uuid>` temp files in `COMFYUI_INPUT_DIR`, never cleaned (also leaks on lock-busy rejection). Clean in a `finally`.
- `generate_dataset`: `count` unclamped — clamp ~1..80.

---

## 7. Uncommitted working-tree changes (decide their fate)

Still uncommitted on the branch at handoff (pre-existing reference-mode/backend work, left untouched):
```
 M docs/superpowers/plans/2026-07-21-casting-studio-frontend.md
 M studio/backend/app/{comfy,config,enrich,git_ops,jobs,models_store,safety,schema}.py
 M studio/backend/tests/{test_enrich,test_git_ops,test_models_store,test_schema}.py
 M studio/frontend/design/mockup.html
 M studio/frontend/src/styles.css
```
Backend suite is green *with* these present. Decide whether they belong on this branch (commit) or a separate one before merging PR #1.

---

## 8. Acceptance bar for the whole feature

Promote **Cecil**, generate her in 3 unrelated scenes (gym / candlelit dinner / blue-hour Paris in a gown) at different seeds → a human confirms it is unmistakably the same Cecil face in all three, matching her reference. Plus: the same LoRA renders her in underwear, a tee, and a gown from prompt alone (wardrobe swap works). This is the bar the reference-only path failed — see the paused project `local-ai-workstation/projects/2026-07-22-cecil-paris-walk/blueprint.md`.
