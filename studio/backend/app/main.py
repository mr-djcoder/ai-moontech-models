from fastapi import FastAPI, HTTPException

from app import comfy, models_store, vram, workflows
from app.config import MODELS_ROOT
from app.jobs import JobStore
from app.schema import (
    Candidate,
    Card,
    GenerateRequest,
    GenerateResponse,
    GenerateSheetRequest,
    JobStatus,
)
from app.safety import ANGLE_PHRASES

app = FastAPI(title="Virtual Model Studio backend")
job_store = JobStore()


@app.get("/health")
def health():
    return {"status": "ok"}


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
                candidates.append(Candidate(
                    url=comfy.output_image_url(img["filename"], img.get("subfolder", "")),
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
