import os
import re
import shutil
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import comfy, git_ops, models_store, vram, workflows
from app.config import MODELS_ROOT
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

app = FastAPI(title="Virtual Model Studio backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
job_store = JobStore()


@app.get("/health")
def health():
    return {"status": "ok"}


def _candidate_source_dir(slug: str) -> Path:
    # In Phase 1, candidate PNGs are written by ComfyUI to its own output dir;
    # the frontend plan will pass the actual job output dir. Placeholder seam
    # kept as a separate function so tests can monkeypatch it without touching
    # the route body.
    from app.config import COMFYUI_OUTPUT_DIR
    return COMFYUI_OUTPUT_DIR


def _run_generate_job(job_id: str, req: GenerateRequest) -> None:
    vram.free_vram()
    try:
        candidates: list[Candidate] = []
        for angle in ANGLE_PHRASES:
            if req.mode == "describe":
                graph = workflows.build_describe_graph(
                    identity_string=req.identity_string, angle=angle,
                    seed=req.seed, count=req.count,
                )
            else:
                graph = workflows.build_reference_graph(
                    ref_image_path=req.ref_image, angle=angle,
                    seed=req.seed, count=req.count, likeness=req.likeness or 0.0,
                )
            prompt_id = comfy.submit(graph)
            entry = comfy.poll_history(prompt_id)
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


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    job_id = job_store.create()
    _run_generate_job(job_id, req)
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


_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


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
        card = Card(
            slug=req.slug, name=req.name, gender=req.gender, status="card",
            identity_string=req.identity_string, seed=req.seed,
            attributes=req.attributes, reference_images=reference_images,
            provenance=req.provenance, release=req.release,
            created=date.today().isoformat(),
        )
        models_store.write_card(MODELS_ROOT, card)
    except Exception as exc:  # noqa: BLE001 - surfaced to caller as ok=False
        shutil.rmtree(models_store.card_dir(MODELS_ROOT, req.slug), ignore_errors=True)
        return SaveResponse(ok=False, reason=str(exc))

    # Git phase is intentionally NOT wrapped: a commit_and_push failure after a
    # successful write is a deferred gap (ledger Finding 3), left as a 500.
    sha = git_ops.commit_and_push(
        MODELS_ROOT.parent, f"models/{req.slug}", f"feat: add model {req.slug}"
    )
    return SaveResponse(ok=True, commit=sha)


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
    _run_generate_job(job_id, gen_req)
    return GenerateResponse(job_id=job_id)


@app.post("/dedup-check", response_model=DedupResponse)
def dedup_check(req: DedupRequest):
    # Phase 1 stub — real mechanism deferred to task #16 (attribute vs
    # embedding similarity, reconciled with model judgment). The frontend
    # banner is real; this always returns no matches for now.
    return DedupResponse(matches=[])
