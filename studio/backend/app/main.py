import os
import re
import shutil
import threading
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from app import comfy, dataset, enrich, git_ops, models_store, vram, workflows
from app.config import (
    COMFY_POLL_DELAY,
    COMFY_POLL_MAX_ATTEMPTS,
    COMFYUI_INPUT_DIR,
    MODELS_ROOT,
)
from app.jobs import JobStore
from app.schema import (
    Candidate,
    Card,
    DedupRequest,
    DedupResponse,
    GenerateRequest,
    GenerateResponse,
    GenerateSheetRequest,
    JobStatus,
    SaveRequest,
    SaveResponse,
)
from app.safety import ANGLE_PHRASES, check_save

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")

app = FastAPI(title="Virtual Model Studio backend")
app.add_middleware(
    CORSMiddleware,
    # Vite picks the next free port (5173, 5174, …) when one is taken, so allow
    # any localhost/127.0.0.1 origin rather than pinning a single dev port.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)
job_store = JobStore()


@app.get("/health")
def health():
    return {"status": "ok"}


_ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


@app.post("/upload")
def upload_reference(file: UploadFile = File(...)):
    # Reference-mode seeding: the image must land in ComfyUI's input/ dir so its
    # LoadImage node can read it by filename (which is what build_reference_graph
    # sets as ref_image). Random filename avoids collisions.
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXT:
        raise HTTPException(status_code=400, detail="unsupported image type")
    name = f"ref_{uuid4().hex}{ext}"
    COMFYUI_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    with (COMFYUI_INPUT_DIR / name).open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return {"ref_image": name}


def _candidate_source_dir(slug: str) -> Path:
    # In Phase 1, candidate PNGs are written by ComfyUI to its own output dir;
    # the frontend plan will pass the actual job output dir. Placeholder seam
    # kept as a separate function so tests can monkeypatch it without touching
    # the route body.
    from app.config import COMFYUI_OUTPUT_DIR
    return COMFYUI_OUTPUT_DIR


def _seed_card_reference(slug: str) -> str:
    """Copy the card's first reference frame into ComfyUI's input dir and return
    the filename build_dataset_graphs should anchor on."""
    try:
        card = models_store.read_card(MODELS_ROOT, slug)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="model not found")
    if not card.reference_images:
        raise HTTPException(status_code=400, detail="model has no reference frames")
    src = (MODELS_ROOT / slug / card.reference_images[0])
    if not src.is_file():
        raise HTTPException(status_code=400, detail="reference frame missing on disk")
    name = f"ds_{uuid4().hex}{src.suffix.lower()}"
    COMFYUI_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, COMFYUI_INPUT_DIR / name)
    return name


# A single ComfyUI + one GPU's worth of VRAM is the shared resource. Only one
# generation may run at a time; a second trigger while one is in flight is
# rejected (via the job's error status) rather than clashing over free/restore.
_generation_lock = threading.Lock()


def _run_generate_job(job_id: str, req: GenerateRequest) -> None:
    if not _generation_lock.acquire(blocking=False):
        job_store.set_error(job_id, "another generation is already running")
        return
    try:
        # Enrich the sparse brief into a detailed photoreal prompt BEFORE freeing
        # VRAM — enrichment needs the local LLM running, and free_vram() stops it
        # to make room for ComfyUI. Describe mode only; reference mode is driven
        # by the image.
        identity = req.identity_string
        if identity:
            # Describe mode has no photo, so expand fully. Reference mode is driven
            # by the real photo — only a light touch, so the description enhances
            # the subject without a long invented paragraph overriding the face/body.
            identity = enrich.enrich_identity(identity, brief=(req.mode == "reference"))
        vram.free_vram()
        try:
            candidates: list[Candidate] = []
            for angle in ANGLE_PHRASES:
                if req.mode == "describe":
                    graph = workflows.build_describe_graph(
                        identity_string=identity, angle=angle,
                        seed=req.seed, count=req.count,
                    )
                else:
                    graph = workflows.build_reference_graph(
                        ref_image_path=req.ref_image, angle=angle,
                        seed=req.seed, count=req.count,
                        identity_string=identity,
                    )
                prompt_id = comfy.submit(graph)
                entry = comfy.poll_history(
                    prompt_id,
                    max_attempts=COMFY_POLL_MAX_ATTEMPTS,
                    delay=COMFY_POLL_DELAY,
                )
                if entry["status"]["status_str"] == "error":
                    job_store.set_error(job_id, f"ComfyUI job failed for angle {angle}")
                    return
                images = next(iter(entry["outputs"].values()))["images"]
                for i, img in enumerate(images):
                    filename = img["filename"]
                    subfolder = img.get("subfolder", "")
                    candidates.append(Candidate(
                        url=comfy.output_image_url(filename, subfolder),
                        filename=filename, subfolder=subfolder,
                        angle=angle, index=i,
                    ))
            job_store.set_result(job_id, candidates)
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller via job status
            job_store.set_error(job_id, str(exc))
        finally:
            vram.restore_model()
    finally:
        _generation_lock.release()


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


def _dispatch_generate_job(job_id: str, req: GenerateRequest) -> None:
    # Run generation off the request thread so the HTTP call returns immediately
    # with a job_id. The frontend then polls /jobs/{id}; a multi-minute render no
    # longer blocks (and gets dropped by) the browser/proxy request.
    threading.Thread(
        target=_run_generate_job, args=(job_id, req), daemon=True
    ).start()


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    job_id = job_store.create()
    _dispatch_generate_job(job_id, req)
    return GenerateResponse(job_id=job_id)


@app.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str):
    try:
        return job_store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")


@app.get("/models", response_model=list[Card])
def get_models():
    return models_store.list_cards(MODELS_ROOT)


@app.get("/models/{slug}", response_model=Card)
def get_model(slug: str):
    try:
        return models_store.read_card(MODELS_ROOT, slug)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="model not found")


@app.post("/models/{slug}/dataset", response_model=GenerateResponse)
def generate_dataset(slug: str, req: dict | None = None):
    if not _SAFE_SEGMENT.match(slug):
        raise HTTPException(status_code=404, detail="model not found")
    try:
        count = int((req or {}).get("count", 40))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="count must be an integer")
    ref_image = _seed_card_reference(slug)
    job_id = job_store.create()
    threading.Thread(
        target=_run_dataset_job, args=(job_id, slug, ref_image, count), daemon=True,
    ).start()
    return GenerateResponse(job_id=job_id)


@app.delete("/models/{slug}")
def delete_model(slug: str):
    # Local file removal only: drop the models/<slug>/ folder from disk. No git
    # commit — the working tree is left dirty for the operator to review/commit.
    # Slug is validated + resolved inside MODELS_ROOT to block path traversal.
    if not _SAFE_SEGMENT.match(slug):
        raise HTTPException(status_code=404, detail="model not found")
    root = MODELS_ROOT.resolve()
    target = (root / slug).resolve()
    if not str(target).startswith(str(root) + os.sep):
        raise HTTPException(status_code=404, detail="model not found")
    try:
        models_store.delete_card(MODELS_ROOT, slug)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="model not found")
    return {"ok": True}


@app.get("/models/{slug}/reference/{filename}")
def model_reference_image(slug: str, filename: str):
    if not _SAFE_SEGMENT.match(slug) or not _SAFE_SEGMENT.match(filename):
        raise HTTPException(status_code=404, detail="reference image not found")
    root = MODELS_ROOT.resolve()
    base = (root / slug / "reference").resolve()
    target = (base / filename).resolve()
    if (
        not str(base).startswith(str(root) + os.sep)
        or not str(target).startswith(str(base) + os.sep)
        or not target.is_file()
    ):
        raise HTTPException(status_code=404, detail="reference image not found")
    return FileResponse(target)


@app.get("/comfy-image")
def comfy_image(filename: str, subfolder: str = "", type: str = "output"):
    # Proxy a freshly-rendered candidate image from ComfyUI. ComfyUI 403s browser
    # cross-origin requests, so the frontend loads candidates from here (same
    # origin as the rest of the API) and the backend fetches them server-to-server.
    if not _SAFE_SEGMENT.match(filename):
        raise HTTPException(status_code=404, detail="image not found")
    if subfolder and not _SAFE_SEGMENT.match(subfolder):
        raise HTTPException(status_code=404, detail="image not found")
    if type not in ("output", "temp", "input"):
        raise HTTPException(status_code=404, detail="image not found")
    try:
        data, content_type = comfy.fetch_output_image(filename, subfolder, type)
    except Exception:  # noqa: BLE001 - upstream/network failure surfaced as 502
        raise HTTPException(status_code=502, detail="comfy image fetch failed")
    return Response(content=data, media_type=content_type)


@app.post("/models", response_model=SaveResponse)
def save_model(req: SaveRequest):
    ok, reason = check_save(
        provenance=req.provenance,
        release=req.release,
        is_real_person_reference=(req.provenance == "likeness-consented"),
        # UNENFORCED in Phase 1: no celebrity/public-figure/stock-face detector exists.
        # The global "refused outright, release or not" rule is real in check_save()'s
        # guard logic, but nothing sets this True yet. Same stub status as dedup (#16).
        # Do not treat check_save's celebrity branch as active protection until a
        # detector task lands.
        is_celebrity_or_public_figure=False,
        age_band=req.attributes.age_band,
    )
    if not ok:
        return SaveResponse(ok=False, reason=reason)

    source_dir = _candidate_source_dir(req.slug)
    # Write phase: copy reference frames + build/write the card. If any step
    # fails (e.g. a picked filename doesn't exist on disk), roll back the
    # partial models/<slug>/ folder so a failed save leaves zero trace instead
    # of a half-written directory with no card.json.
    try:
        reference_images = models_store.copy_reference_frames(
            MODELS_ROOT, req.slug, req.picked, source_dir
        )
        # Sanitize before persisting: strip subjective/judgmental commentary so the
        # stored card holds only concrete visual attributes (best-effort — falls
        # back to the raw string if the local LLM is unavailable).
        stored_identity = enrich.sanitize_description(req.identity_string)
        card = Card(
            slug=req.slug, name=req.name, gender=req.gender, status="card",
            identity_string=stored_identity, seed=req.seed,
            attributes=req.attributes, reference_images=reference_images,
            provenance=req.provenance, release=req.release,
            created=date.today().isoformat(),
        )
        models_store.write_card(MODELS_ROOT, card)
    except Exception as exc:  # noqa: BLE001 - surfaced to caller as ok=False
        shutil.rmtree(models_store.card_dir(MODELS_ROOT, req.slug), ignore_errors=True)
        return SaveResponse(ok=False, reason=str(exc))

    # Git phase: a local commit is the durable save. A push failure (e.g. branch
    # has no upstream) is reported as a warning, not a 500 — the model is already
    # committed on disk (ledger Finding 3, now closed).
    sha, push_warning = git_ops.commit_and_push(
        MODELS_ROOT.parent, f"models/{req.slug}", f"feat: add model {req.slug}"
    )
    return SaveResponse(ok=True, commit=sha, warning=push_warning)


@app.post("/generate-sheet", response_model=GenerateResponse)
def generate_sheet(req: GenerateSheetRequest):
    try:
        card = models_store.read_card(MODELS_ROOT, req.slug)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="model not found")
    gen_req = GenerateRequest(
        mode="describe", identity_string=card.identity_string,
        seed=card.seed, count=8,
    )
    job_id = job_store.create()
    _dispatch_generate_job(job_id, gen_req)
    return GenerateResponse(job_id=job_id)


@app.post("/dedup-check", response_model=DedupResponse)
def dedup_check(req: DedupRequest):
    # Phase 1 stub — real mechanism deferred to task #16 (attribute vs
    # embedding similarity, reconciled with model judgment). The frontend
    # banner is real; this always returns no matches for now.
    return DedupResponse(matches=[])
