# LoRA Identity-Lock — Phase A: Dataset Generation + Curation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Given a saved `card`-status model, generate a varied, on-identity image dataset (the raw material a LoRA needs) and let the user curate it — reusing the proven 2511 reference pipeline, the job store, and the VRAM broker.

**Architecture:** A new pure `dataset.py` builds a deterministic variant matrix (angle × lighting × distance) and reuses `workflows.build_reference_graph` (extended with an optional `extra` modifier) to produce ~40 candidates anchored on the model's saved front reference frame. A new `POST /models/{slug}/dataset` endpoint runs it as a background job (same pattern as `/generate`), returning `Candidate`s the existing grid can curate.

**Tech Stack:** Python 3.12 / FastAPI / pytest (backend). ComfyUI Qwen-Image-Edit-2511 graph (existing). No new dependencies.

## Global Constraints

- Backend is localhost-only, no auth. Do not add auth/deployment/non-localhost config.
- All existing backend tests MUST stay green. Changes are additive.
- Reuse the existing single-GPU discipline: one heavy op at a time via `_generation_lock`, and `vram.free_vram()` / `vram.restore_model()` around ComfyUI work (see `_run_generate_job` in `studio/backend/app/main.py`).
- ComfyUI reads reference uploads by filename from `COMFYUI_INPUT_DIR` (see `/upload` in `main.py:55`).
- Dataset stays wardrobe-neutral; variety is angle × lighting × distance only (expression variety is deferred — it fights the reference pipeline's neutral-expression base).
- Spec: `docs/superpowers/specs/2026-07-22-model-studio-lora-identity-lock.md`.
- Reference pipeline entry point: `workflows.build_reference_graph(ref_image_path, angle, seed, count, identity_string=None)`.
- Angles are the four keys of `safety.ANGLE_PHRASES`: `front`, `34`, `profile`, `body`.

---

### Task 1: `build_reference_graph` accepts an optional `extra` modifier

**Files:**
- Modify: `studio/backend/app/workflows.py` (`build_reference_graph`)
- Test: `studio/backend/tests/test_workflows.py` (append)

**Interfaces:**
- Consumes: existing `build_reference_graph(ref_image_path, angle, seed, count, identity_string=None)`.
- Produces: `build_reference_graph(ref_image_path, angle, seed, count, identity_string=None, extra="")` — when `extra` is non-empty it is injected into the positive prompt (node 5) as an additional comma-clause after the house style; empty `extra` yields a prompt byte-identical to before.

- [ ] **Step 1: Write the failing test**

Append to `studio/backend/tests/test_workflows.py`:

```python
def test_reference_graph_injects_extra_modifier():
    base = workflows.build_reference_graph(
        ref_image_path="r.png", angle="front", seed=1, count=1,
    )["5"]["inputs"]["prompt"]
    withx = workflows.build_reference_graph(
        ref_image_path="r.png", angle="front", seed=1, count=1,
        extra="warm side lighting, close head-and-shoulders framing",
    )["5"]["inputs"]["prompt"]
    assert "warm side lighting, close head-and-shoulders framing" in withx
    assert withx != base


def test_reference_graph_empty_extra_is_unchanged():
    base = workflows.build_reference_graph(
        ref_image_path="r.png", angle="body", seed=7, count=2,
    )["5"]["inputs"]["prompt"]
    same = workflows.build_reference_graph(
        ref_image_path="r.png", angle="body", seed=7, count=2, extra="",
    )["5"]["inputs"]["prompt"]
    assert base == same
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd studio/backend && python -m pytest tests/test_workflows.py::test_reference_graph_injects_extra_modifier -v`
Expected: FAIL — `build_reference_graph() got an unexpected keyword argument 'extra'`.

- [ ] **Step 3: Implement the minimal change**

In `studio/backend/app/workflows.py`, change the `build_reference_graph` signature and the node-5 prompt assembly. Update the signature line:

```python
def build_reference_graph(
    ref_image_path: str, angle: str, seed: int, count: int,
    identity_string: str | None = None, extra: str = "",
) -> dict:
```

Then, where the positive prompt is assembled (the `graph["5"]["inputs"]["prompt"] = (...)` block), append the modifier immediately before the wardrobe/quality tail:

```python
    extra_clause = f"{extra.strip()}, " if extra and extra.strip() else ""
    graph["5"]["inputs"]["prompt"] = (
        f"{phrase}, {pose}, "
        f"{_IDENTITY_CLAUSE}, {_BODY_CLAUSE}, {refine}{face_clause}"
        f"{_PORTRAIT_BASE}, {_REFRAME_CLAUSE}, {_ANGLE_FRAMING}, "
        f"{extra_clause}"
        f"{_WARDROBE}, {_QUALITY_TAIL}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd studio/backend && python -m pytest tests/test_workflows.py -v`
Expected: PASS (all prior workflow tests + the two new ones).

- [ ] **Step 5: Commit**

```bash
git add studio/backend/app/workflows.py studio/backend/tests/test_workflows.py
git commit -m "feat(studio): optional extra-modifier clause in reference graph"
```

---

### Task 2: `dataset.py` — pure variant matrix

**Files:**
- Create: `studio/backend/app/dataset.py`
- Test: `studio/backend/tests/test_dataset.py`

**Interfaces:**
- Produces:
  - `DatasetVariant` — a `dataclass(frozen=True)` with fields `angle: str`, `extra: str`, `seed: int`.
  - `dataset_variants(base_seed: int, count: int = 40) -> list[DatasetVariant]` — a deterministic matrix over the four angles × a fixed lighting list × a fixed distance list, each with a distinct derived seed; returns at most `count` variants (round-robin across angles so every angle is represented before any repeats).

- [ ] **Step 1: Write the failing test**

Create `studio/backend/tests/test_dataset.py`:

```python
from app import dataset


def test_variants_deterministic_and_capped():
    a = dataset.dataset_variants(base_seed=1000, count=40)
    b = dataset.dataset_variants(base_seed=1000, count=40)
    assert a == b                      # deterministic
    assert len(a) == 40                # capped to requested count
    assert len(set(v.seed for v in a)) == 40   # every variant a distinct seed


def test_variants_cover_all_four_angles_before_repeating():
    v = dataset.dataset_variants(base_seed=1, count=4)
    assert {x.angle for x in v} == {"front", "34", "profile", "body"}


def test_variants_carry_lighting_and_distance_in_extra():
    v = dataset.dataset_variants(base_seed=1, count=40)
    # every variant's extra names one lighting and one distance token
    assert all(v0.extra.strip() for v0 in v)
    joined = " ".join(x.extra for x in v)
    assert "lighting" in joined
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd studio/backend && python -m pytest tests/test_dataset.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.dataset'`.

- [ ] **Step 3: Implement**

Create `studio/backend/app/dataset.py`:

```python
from dataclasses import dataclass

from app.safety import ANGLE_PHRASES

# Variety axes for a character LoRA dataset. Wardrobe stays neutral (captioned
# separately at training time); expression stays neutral (the reference pipeline
# forces it). We vary what we safely can: angle, lighting, and shot distance.
_ANGLES = list(ANGLE_PHRASES)  # front, 34, profile, body
_LIGHTING = [
    "soft even studio lighting",
    "warm side lighting",
    "cool window light from one side",
]
_DISTANCE = [
    "close head-and-shoulders framing",
    "mid three-quarter framing",
]


@dataclass(frozen=True)
class DatasetVariant:
    angle: str
    extra: str
    seed: int


def dataset_variants(base_seed: int, count: int = 40) -> list[DatasetVariant]:
    """Deterministic angle x lighting x distance matrix, round-robin by angle so
    every angle appears before any repeats. Each variant gets a distinct seed
    derived from base_seed for reproducibility."""
    combos: list[tuple[str, str]] = []
    for light in _LIGHTING:
        for dist in _DISTANCE:
            combos.append((light, dist))
    variants: list[DatasetVariant] = []
    i = 0
    # Outer loop over combos, inner over angles -> angles cycle fastest.
    for light, dist in combos:
        for angle in _ANGLES:
            if len(variants) >= count:
                return variants
            variants.append(DatasetVariant(
                angle=angle,
                extra=f"{light}, {dist}",
                seed=base_seed + i,
            ))
            i += 1
    return variants
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd studio/backend && python -m pytest tests/test_dataset.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add studio/backend/app/dataset.py studio/backend/tests/test_dataset.py
git commit -m "feat(studio): dataset variant matrix for LoRA training set"
```

---

### Task 3: `dataset.py` — build the per-variant graphs from a card

**Files:**
- Modify: `studio/backend/app/dataset.py`
- Test: `studio/backend/tests/test_dataset.py` (append)

**Interfaces:**
- Consumes: `dataset_variants`, `workflows.build_reference_graph`.
- Produces: `build_dataset_graphs(ref_image: str, identity_string: str | None, base_seed: int, count: int = 40) -> list[tuple[DatasetVariant, dict]]` — one ComfyUI graph per variant, each anchored on `ref_image` (a filename already present in ComfyUI's input dir), `count=1` per graph, with the variant's `extra` injected. Pure: builds dicts, submits nothing.

- [ ] **Step 1: Write the failing test**

Append to `studio/backend/tests/test_dataset.py`:

```python
def test_build_dataset_graphs_one_per_variant_anchored_on_ref():
    graphs = dataset.build_dataset_graphs(
        ref_image="ref_abc.png", identity_string="a Filipino woman, mid 40s",
        base_seed=500, count=8,
    )
    assert len(graphs) == 8
    for variant, graph in graphs:
        assert graph["2"]["inputs"]["image"] == "ref_abc.png"   # anchored
        assert graph["7"]["inputs"]["batch_size"] == 1          # one image each
        assert graph["8"]["inputs"]["seed"] == variant.seed     # variant seed
        assert variant.extra in graph["5"]["inputs"]["prompt"]  # modifier applied
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd studio/backend && python -m pytest tests/test_dataset.py::test_build_dataset_graphs_one_per_variant_anchored_on_ref -v`
Expected: FAIL — `AttributeError: module 'app.dataset' has no attribute 'build_dataset_graphs'`.

- [ ] **Step 3: Implement**

Append to `studio/backend/app/dataset.py`:

```python
from app import workflows


def build_dataset_graphs(
    ref_image: str, identity_string: str | None, base_seed: int, count: int = 40,
) -> list[tuple[DatasetVariant, dict]]:
    """One reference graph per variant, anchored on ref_image, batch of 1."""
    out: list[tuple[DatasetVariant, dict]] = []
    for variant in dataset_variants(base_seed, count):
        graph = workflows.build_reference_graph(
            ref_image_path=ref_image, angle=variant.angle, seed=variant.seed,
            count=1, identity_string=identity_string, extra=variant.extra,
        )
        out.append((variant, graph))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd studio/backend && python -m pytest tests/test_dataset.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add studio/backend/app/dataset.py studio/backend/tests/test_dataset.py
git commit -m "feat(studio): build per-variant dataset graphs from a card ref"
```

---

### Task 4: `POST /models/{slug}/dataset` endpoint (background job)

**Files:**
- Modify: `studio/backend/app/main.py`
- Test: `studio/backend/tests/test_api.py` (append)

**Interfaces:**
- Consumes: `dataset.build_dataset_graphs`, `models_store.read_card`, `job_store`, `comfy.submit`/`poll_history`, `vram`, `_generation_lock`.
- Produces: `POST /models/{slug}/dataset` with JSON body `{ "count": int }` (default 40) → `GenerateResponse{ job_id }`. Job result is a list of `Candidate` (one per rendered image; `angle` = the variant angle, `index` = ordinal). Anchors on the card's first `reference_images` frame, copied into `COMFYUI_INPUT_DIR`.

- [ ] **Step 1: Write the failing test**

Append to `studio/backend/tests/test_api.py` (follow the existing monkeypatch style used by the `/generate` tests):

```python
def test_dataset_endpoint_runs_job_and_returns_candidates(monkeypatch, tmp_path):
    from app import main, models_store
    from app.schema import Attributes, Card

    # A saved card on disk with one reference frame.
    card = Card(
        slug="cecil", name="Cecil", gender="Female", status="card",
        identity_string="a Filipino woman, mid 40s", seed=123,
        attributes=Attributes(age_band="mid 40s"),
        reference_images=["reference/front.png"], provenance="synthetic",
        created="2026-07-22",
    )
    monkeypatch.setattr(main.models_store, "read_card", lambda root, slug: card)
    # Reference frame source file exists so the copy-into-input step succeeds.
    ref_src = tmp_path / "cecil" / "reference"
    ref_src.mkdir(parents=True)
    (ref_src / "front.png").write_bytes(b"png")
    monkeypatch.setattr(main, "MODELS_ROOT", tmp_path)
    monkeypatch.setattr(main, "COMFYUI_INPUT_DIR", tmp_path / "input")

    monkeypatch.setattr(main.vram, "free_vram", lambda: None)
    monkeypatch.setattr(main.vram, "restore_model", lambda: None)
    monkeypatch.setattr(main.comfy, "submit", lambda graph: "pid")

    def fake_poll(prompt_id, **kw):
        return {"status": {"status_str": "success"},
                "outputs": {"11": {"images": [
                    {"filename": "sheet_ref_front_0.png", "subfolder": "job"}]}}}
    monkeypatch.setattr(main.comfy, "poll_history", fake_poll)

    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    r = client.post("/models/cecil/dataset", json={"count": 4})
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    # Job runs on a background thread; poll to completion.
    import time
    for _ in range(50):
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.02)
    assert job["status"] == "done"
    assert len(job["candidates"]) == 4
    assert job["candidates"][0]["filename"] == "sheet_ref_front_0.png"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd studio/backend && python -m pytest tests/test_api.py::test_dataset_endpoint_runs_job_and_returns_candidates -v`
Expected: FAIL — 404 (route not defined).

- [ ] **Step 3: Implement**

In `studio/backend/app/main.py`, add a reference-seeding helper and the endpoint. Add near `_candidate_source_dir` (uses already-imported `shutil`, `uuid4`, `Path`, `MODELS_ROOT`, `COMFYUI_INPUT_DIR`):

```python
def _seed_card_reference(slug: str) -> str:
    """Copy the card's first reference frame into ComfyUI's input dir and return
    the filename build_dataset_graphs should anchor on."""
    card = models_store.read_card(MODELS_ROOT, slug)
    if not card.reference_images:
        raise HTTPException(status_code=400, detail="model has no reference frames")
    src = (MODELS_ROOT / slug / card.reference_images[0])
    if not src.is_file():
        raise HTTPException(status_code=400, detail="reference frame missing on disk")
    name = f"ds_{uuid4().hex}{src.suffix.lower()}"
    COMFYUI_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, COMFYUI_INPUT_DIR / name)
    return name


def _run_dataset_job(job_id: str, slug: str, ref_image: str, count: int) -> None:
    if not _generation_lock.acquire(blocking=False):
        job_store.set_error(job_id, "another generation is already running")
        return
    try:
        card = models_store.read_card(MODELS_ROOT, slug)
        vram.free_vram()
        try:
            graphs = dataset.build_dataset_graphs(
                ref_image=ref_image, identity_string=card.identity_string,
                base_seed=card.seed, count=count,
            )
            candidates: list[Candidate] = []
            for idx, (variant, graph) in enumerate(graphs):
                prompt_id = comfy.submit(graph)
                entry = comfy.poll_history(
                    prompt_id, max_attempts=COMFY_POLL_MAX_ATTEMPTS,
                    delay=COMFY_POLL_DELAY,
                )
                if entry["status"]["status_str"] == "error":
                    job_store.set_error(job_id, f"ComfyUI failed on variant {idx}")
                    return
                images = next(iter(entry["outputs"].values()))["images"]
                for img in images:
                    candidates.append(Candidate(
                        url=comfy.output_image_url(img["filename"], img.get("subfolder", "")),
                        filename=img["filename"], subfolder=img.get("subfolder", ""),
                        angle=variant.angle, index=idx,
                    ))
            job_store.set_result(job_id, candidates)
        except Exception as exc:  # noqa: BLE001
            job_store.set_error(job_id, str(exc))
        finally:
            vram.restore_model()
    finally:
        _generation_lock.release()


@app.post("/models/{slug}/dataset", response_model=GenerateResponse)
def generate_dataset(slug: str, req: dict | None = None):
    if not _SAFE_SEGMENT.match(slug):
        raise HTTPException(status_code=404, detail="model not found")
    count = int((req or {}).get("count", 40))
    ref_image = _seed_card_reference(slug)
    job_id = job_store.create()
    threading.Thread(
        target=_run_dataset_job, args=(job_id, slug, ref_image, count), daemon=True,
    ).start()
    return GenerateResponse(job_id=job_id)
```

Add `dataset` to the existing app import line:

```python
from app import comfy, dataset, enrich, git_ops, models_store, vram, workflows
```

(`_SAFE_SEGMENT` is already defined later in the file for `delete_model`; if the endpoint is placed above it, move the `_SAFE_SEGMENT = re.compile(...)` line up to just under the imports so both routes see it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd studio/backend && python -m pytest tests/test_api.py -v`
Expected: PASS (all existing API tests + the new dataset test).

- [ ] **Step 5: Run the full suite**

Run: `cd studio/backend && python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add studio/backend/app/main.py studio/backend/tests/test_api.py
git commit -m "feat(studio): POST /models/{slug}/dataset background job"
```

---

### Task 5: Frontend — dataset generate + curate in a Train panel

**Files:**
- Create: `studio/frontend/src/routes/Train.jsx`
- Modify: `studio/frontend/src/api.js` (add `generateDataset`)
- Modify: `studio/frontend/src/routes/ModelDetail.jsx` (enable "Promote to LoRA" → link to `/model/:slug/train`)
- Modify: `studio/frontend/src/main.jsx` or the router file (add the `/model/:slug/train` route — match the existing route-registration pattern)

**Interfaces:**
- Consumes: `POST /models/:slug/dataset` via `generateDataset`, `pollUntilDone`, `CandidateGrid`.
- Produces: a Train route that generates the dataset, shows the candidate grid, and lets the user multi-select keepers into local state `kept` (a `Set` of `filename`). Curation is client-side only in Phase A; the kept set is handed to Phase B's train call (not yet wired — a disabled "Train LoRA" button shows the kept count).

- [ ] **Step 1: Add the API function**

In `studio/frontend/src/api.js`, add:

```javascript
export const generateDataset = (slug, count = 40) =>
  jpost(`/models/${slug}/dataset`, { count });
```

- [ ] **Step 2: Create the Train route**

Create `studio/frontend/src/routes/Train.jsx`:

```jsx
import { useState } from "react";
import { useParams } from "react-router-dom";
import { generateDataset, pollUntilDone } from "../api.js";
import CandidateGrid from "../components/CandidateGrid.jsx";

export default function Train() {
  const { slug } = useParams();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [kept, setKept] = useState(() => new Set());

  async function run() {
    setBusy(true); setError(null); setCandidates([]); setKept(new Set());
    try {
      const { job_id } = await generateDataset(slug, 40);
      const job = await pollUntilDone(job_id);
      if (job.status === "error") { setError(job.error || "dataset failed"); return; }
      setCandidates(job.candidates);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  function toggle(filename) {
    setKept((prev) => {
      const next = new Set(prev);
      next.has(filename) ? next.delete(filename) : next.add(filename);
      return next;
    });
  }

  return (
    <section id="train">
      <div className="sec-head"><h2>Train LoRA — {slug}</h2></div>
      <div className="pane">
        <div className="body">
          <button className="btn primary" onClick={run} disabled={busy}>
            {busy ? "Generating dataset…" : "⟳ Generate dataset (40)"}
          </button>
          {error && <div className="alert warn"><b>Failed.</b> {error}</div>}
          {candidates.length > 0 && (
            <>
              <div className="note"><span className="dot"></span>
                <span>Pick the on-identity keepers ({kept.size} kept · need ≥15).</span></div>
              <CandidateGrid
                candidates={candidates}
                picked={Object.fromEntries([...kept].map((f) => [f, f]))}
                onPick={(_, f) => toggle(f)}
                multi
              />
              <button className="btn ok" disabled title="Phase B">
                Train LoRA · {kept.size} images
              </button>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
```

Note: `CandidateGrid` in Phase A is reused for display; if its current props don't support multi-select, adapt the call to its actual signature (read `studio/frontend/src/components/CandidateGrid.jsx` first). Keep the kept-set logic here regardless.

- [ ] **Step 3: Register the route**

In the router registration (match how `/model/:slug` is registered), add:

```jsx
<Route path="/model/:slug/train" element={<Train />} />
```

and enable the Promote button in `ModelDetail.jsx` to navigate there (replace its `disabled` with a `Link`/`navigate` to `/model/${slug}/train`).

- [ ] **Step 4: Manual verification**

Run the backend (`uvicorn app.main:app --reload --port 8800`) and frontend (`npm run dev`), open a saved model, click **Promote to LoRA → Generate dataset**, confirm a grid of ~40 varied Cecil frames renders and keepers toggle. (No automated frontend test in this repo's Phase A.)

- [ ] **Step 5: Commit**

```bash
git add studio/frontend/src/routes/Train.jsx studio/frontend/src/api.js studio/frontend/src/routes/ModelDetail.jsx
git commit -m "feat(studio): Train route — dataset generate + curate"
```

---

## Phase A self-check

- Dataset variety: angle × lighting × distance, deterministic, capped, distinct seeds (Tasks 2–3).
- Anchored on the model's real reference frame (Task 4).
- Reuses job store, VRAM broker, single-GPU lock (Task 4).
- Curation grid with a kept-set ≥15 gate surfaced (Task 5).

## Follow-on plans (do NOT start until Phase A ships)

**Phase B — training + validation + publish.** Blocked on a live-server spike: open ComfyUI, add a `TrainLoraNode`, and record its exact list-input wiring (how a list of dataset latents and a list of caption conditionings are constructed in an API graph), `SaveLoRA` params, and VRAM behavior of the fp8 Qwen-Image base with `training_dtype: none`. Only then write `train_graph.py`, `captions.py`, `train_jobs.py`, `pack.py`, the promote endpoint, and the validation gate. Plan file: `docs/superpowers/plans/2026-07-22-lora-phase-b-train.md`.

**Phase C — consumption + skill wiring.** `qwen-txt2img-lora.json`, status-branched generation dispatch (`lora` → txt2img+LoRA+trigger; `card` → reference-edit), `ai-moontech-media-studio` skill branch, roster/detail LoRA display. Plan file: `docs/superpowers/plans/2026-07-22-lora-phase-c-consume.md`.
