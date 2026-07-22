# Design spec — Model Studio: LoRA identity-lock (card → lora promotion)

Date: 2026-07-22. Status: **designed / ready to plan.** Supersedes the earlier handoff draft of the
same name. Purpose: give a Model Studio model the one capability reference-only generation cannot —
**locking a model's exact identity and holding it across arbitrary new scenes, wardrobe, pose, and
seed** — via a per-model trained LoRA, produced and consumed entirely inside the existing
ComfyUI + FastAPI studio.

## Why this exists (proven, not theoretical)

Two real builds hit the same wall on the reference-only path (Qwen-Image-Edit with the model's
`reference/` frames as image conditioning):

1. **Date Night ad recast to Cecil** — face drifted shot-to-shot; "a mid-40s Filipino woman," not
   Cecil's specific face.
2. **Cecil / Paris blue-hour walk** — same. Every seed produced a *different* face in Cecil's
   ballpark; feeding the wardrobe photo as a 2nd reference made a *slim young model* appear instead
   of Cecil (the stronger reference won).

Root cause: **Qwen-Image-Edit reference images nudge, they do not pin.** At `denoise 1.0` into a
fresh scene the reference only loosely conditions; identity is re-invented per seed. Two failures
fall out, and the studio must solve both:

- **Consistency** — the SAME face across many generations.
- **Adaptation** — a NEW scene/wardrobe/pose while keeping the face. High denoise adapts the scene
  but loses the face; low denoise keeps the face but drags the reference's background/wardrobe. No
  usable middle.

A per-model LoRA encodes identity in weights, not in a conditioning image, so identity survives
arbitrary prompts, scenes, wardrobe, and seeds. This is the only reliable fix.

## Key design decisions (from brainstorming 2026-07-22)

1. **Trainer = ComfyUI-native `TrainLoraNode`.** ComfyUI ships built-in LoRA training
   (`comfy_extras/nodes_train.py`: `TrainLoraNode`, `SaveLoRA`, `LossGraphNode`). Training is just
   another graph we `comfy.submit()` and `poll_history()` — same transport, same VRAM broker as
   generation. **No musubi-tuner, no external trainer, no subprocess, no TOML.**
2. **Base model = Qwen-Image (txt2img), not the Edit model.** Train the LoRA on
   `qwen_image_fp8_e4m3fn.safetensors` and consume via a plain Qwen **txt2img** graph + LoRA +
   trigger. Identity comes from weights, so scene/wardrobe/pose are fully free — this fixes
   adaptation and consistency at once. The reference-edit path stays as the `card` fallback.
3. **Dataset = auto-generate + curate.** Generate ~40 varied on-identity stills via the fixed 2511
   reference pipeline (front/34/profile/body already proven), user curates ≥20 keepers in the
   existing candidate grid. Bad frames never reach training.
4. **Wardrobe stays swappable via captioning discipline.** Dataset is wardrobe-neutral (the studio's
   plain underwear base); **every caption explicitly names the wardrobe**, so clothing stays a
   *variable* the trigger does not absorb. Backgrounds/lighting/pose are varied; wardrobe is neutral
   but always captioned. (LoRA rule: captioned attributes stay editable; uncaptioned attributes bake
   into the trigger — so the face, left undescribed beyond the trigger, is what gets locked.)
5. **Output = a reusable content pack**, not just a raw file (see Content pack).
6. **Human validation gate** before the status flip: after training, auto-render a test with the
   LoRA applied; status only flips to `lora` once the user approves it.

## Data model (card.json additions)

Extend `Card` in `studio/backend/app/schema.py` (backward compatible — optional until promoted):

```
lora: Optional[LoraInfo] = None      # present once status == "lora"

class LoraInfo(BaseModel):
    file: str            # comfyui-relative lora name, e.g. "cecil.safetensors"
    base_model: str      # "qwen-image"
    trigger: str         # unique token in captions, e.g. "cecil_moontech_woman"
    steps: int
    rank: int
    trained: str         # ISO date
    dataset_size: int    # curated image count used
    strength_default: float = 1.0
```

The trained `.safetensors` lives in ComfyUI `models/loras/<slug>.safetensors` (where generation
loads it). The per-model **content pack** copy + metadata live under `models/<slug>/lora/`. LoRA
binaries are **not** committed raw to git history — use git-LFS or a release asset (decide at build).

## Components (new/changed, each isolated + testable)

Backend (`studio/backend/app/`):

- **`dataset.py`** — pure prompt-matrix builder (angle × expression × lighting × distance × framing,
  wardrobe held neutral) + a thin driver that reuses `workflows.build_reference_graph` and
  `comfy.submit`. The matrix builder is pure/unit-tested; the driver is a thin loop.
- **`captions.py`** — pure. Trigger token + per-image caption ("<trigger>, <neutral identity>,
  wearing plain beige underwear, <angle/lighting>"). Wardrobe always named.
- **`train_graph.py`** — pure builder of the ComfyUI training graph: load Qwen-Image base → per
  curated image `LoadImage`→`VAEEncode`→latent list, per caption text-encode→conditioning list →
  `TrainLoraNode`(rank, steps, lr, training_dtype) → `SaveLoRA`. **Verify list-input construction
  and exact node params against the live `TrainLoraNode` before wiring — do not guess.**
- **`train_jobs.py`** — extends the existing job store with phases:
  `generating → curating → training → validating → publishing`, with progress/log.
- **`pack.py`** — pure. Assembles the content pack (manifest + snippet graphs) from a promoted card.
- **`main.py`** — endpoints (below), gated by the VRAM broker (`vram.py`), one heavy op at a time.

Workflows (`studio/backend/workflows/`):

- **`qwen-lora-train.json`** — the training graph template.
- **`qwen-txt2img-lora.json`** — consumption graph: Qwen-Image base + `LoraLoaderModelOnly` +
  trigger, plain txt2img (full scene freedom).

Frontend (`studio/frontend/src/`):

- **`TrainPanel.jsx`** — behind the now-enabled "Promote to LoRA" button: generate dataset → curate
  (reuse `CandidateGrid`) → train (live progress/log) → validation render → approve/publish.
- Roster/detail: `LoRA` status stamp already exists (`ModelCard.jsx`, `Roster.jsx`) — just driven by
  real `status`.

## Training graph (mechanism)

`TrainLoraNode` (`model/training`, experimental, `is_input_list=True`): inputs are `model`, a **list**
of `latents` (dataset), a **list** of `positive` conditionings (captions), plus `batch_size`,
`grad_accumulation_steps`, `steps`, `learning_rate`, `rank` (≤128), `optimizer` (AdamW),
`loss_function` (MSE), `seed`, `training_dtype` (bf16/fp32/none). `SaveLoRA` writes to
`models/loras/`. Load the **fp8** Qwen-Image base and use `training_dtype: none` (preserve native
compute dtype) to fit the 34 GB card; tune `rank`/`grad_accumulation_steps` if VRAM is tight.
Starting point: rank 16–32, ~2000 steps, lr ~1e-4, batch 1. Training monopolizes the GPU
(~30–90 min) — reuse the one-pipeline lock + `free_vram`/`restore_model`.

## Generation consumption (the payoff — seamless)

Once `status == "lora"`, EVERY generation for that model uses the txt2img+LoRA path, replacing
reference conditioning:

- Load Qwen-Image base; insert `LoraLoaderModelOnly` (lora = `card.lora.file`, strength =
  `strength_default`) between UNet loader and `ModelSamplingAuraFlow`.
- Prepend `card.lora.trigger` to every positive prompt.
- Plain txt2img — scene/wardrobe/pose fully free.
- **Clothing:** prompt the outfit (`<trigger> ... wearing a wine-red gown`), or for a *specific*
  garment use the Edit graph with `TextEncodeQwenImageEditPlus` (image1 = a LoRA render, image2 =
  garment ref). The content pack ships both a plain and a "dress her" snippet.
- `status == "card"` (un-promoted) models keep the current reference-edit path.

The `ai-moontech-media-studio` skill's `model: <slug>` lookup branches on status: `lora` →
txt2img+LoRA+trigger; `card` → reference-edit. No per-build wiring — a promoted model is locked
everywhere automatically.

## Content pack (published output)

Written to `models/<slug>/lora/` (+ LoRA copied to ComfyUI `models/loras/`):

- `<slug>.safetensors` — the LoRA
- trigger + `LoraInfo` in `card.json` (`status:"lora"`)
- `frame-plain.json` — txt2img + LoRA + trigger snippet
- `frame-dress.json` — LoRA identity + garment-ref (Edit) snippet
- sample contact sheet — the validation renders
- `pack.md` — manifest: trigger word, strength, how to drop the character into any project

## API

- `POST /models/{slug}/train/dataset` → generate the candidate dataset; returns `job_id`. Curated
  picks posted back (reuse candidate/pick shapes).
- `POST /models/{slug}/train` → caption + build training graph + train + validation render; returns
  `job_id`; progress via `GET /jobs/{id}` with the new phases.
- `POST /models/{slug}/promote` → on user approval of the validation render: publish pack, write
  `LoraInfo`, flip `status`.
- `GET /models/{slug}` already returns the card; frontend reads `status` + `lora`.

## Error handling / gates

- **<15 curated images** → block training with guidance.
- **Training failure** (OOM / node error) → surface ComfyUI log tail, restore VRAM, stay `card`.
- **VRAM** → fp8 base + `training_dtype: none` + grad-accumulation; documented knobs (rank, steps).
- **No status flip until the user approves the validation render.**

## Testing

- Pure units: prompt-matrix (`dataset.py`), captions, `train_graph.py` (node wiring + params),
  `pack.py` manifest — unit-tested, no GPU.
- Job phase transitions tested with fakes (existing `test_api` monkeypatch pattern).
- Schema back-compat: old cards (no `lora`) still validate.
- No live GPU/training in the test suite.

## Phasing

- **Phase A** — dataset generation + curation (`dataset.py`, `captions.py`, dataset endpoint,
  `TrainPanel` generate/curate).
- **Phase B** — training + validation + publish + pack (`train_graph.py`, `train_jobs.py`,
  `pack.py`, `qwen-lora-train.json`, promote endpoint, validation gate).
- **Phase C** — consumption wiring (`qwen-txt2img-lora.json`, status-branched gen dispatch,
  media-studio skill branch, roster/detail LoRA display).

## Acceptance

Promote **Cecil**, then generate her in 3 unrelated scenes (gym / candlelit dinner / blue-hour Paris
in a gown) at different seeds. **Pass = a human confirms it is unmistakably the same Cecil face in
all three, matching her reference.** That is the bar the reference-only path failed. Re-verify
clothing swap: the same LoRA renders her in underwear, a tee, and a gown from prompt alone.

## Interim (until this ships)

The Cecil / Paris video stays **paused** on the reference-only path. Resume it (and re-do the Cecil
ad) once promotion lands. Blueprint:
`local-ai-workstation/projects/2026-07-22-cecil-paris-walk/blueprint.md`.
