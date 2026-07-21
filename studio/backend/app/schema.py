from typing import Literal, Optional
from pydantic import BaseModel

Status = Literal["card", "lora"]
Provenance = Literal["synthetic", "likeness-consented"]
GenerateMode = Literal["describe", "reference"]
JobState = Literal["running", "done", "error"]


class Attributes(BaseModel):
    race_ethnicity: str = ""
    age_band: str
    height: str = ""
    build: str = ""
    hair: str = ""
    distinctive_face: str = ""
    distinctive_body: str = ""
    personality: str = ""


class Release(BaseModel):
    subject: str
    date: str
    consent: bool
    statement: str
    file: str


class Card(BaseModel):
    slug: str
    name: str
    gender: str
    status: Status
    identity_string: str
    seed: int
    attributes: Attributes
    base_wardrobe: str = "plain neutral underwear set"
    reference_images: list[str]
    provenance: Provenance
    release: Optional[Release] = None
    created: str


class GenerateRequest(BaseModel):
    mode: GenerateMode
    attributes: Optional[Attributes] = None
    identity_string: Optional[str] = None
    seed: Optional[int] = None
    ref_image: Optional[str] = None
    likeness: Optional[float] = None
    count: int = 8


class Candidate(BaseModel):
    url: str
    angle: str
    index: int


class GenerateResponse(BaseModel):
    job_id: str


class JobStatus(BaseModel):
    status: JobState
    candidates: list[Candidate] = []
    error: Optional[str] = None


class PickedFrames(BaseModel):
    front: str
    profile: str
    body: str
    # NOTE: "34" (three-quarter) is not a valid Python identifier, handled via
    # the raw dict form in SaveRequest.picked instead of a named field here.


class SaveRequest(BaseModel):
    slug: str
    name: str
    gender: str
    identity_string: str
    seed: int
    attributes: Attributes
    provenance: Provenance
    release: Optional[Release] = None
    picked: dict[str, str]  # keys: front, 34, profile, body -> candidate url/path


class SaveResponse(BaseModel):
    ok: bool
    commit: Optional[str] = None
    reason: Optional[str] = None


class DedupRequest(BaseModel):
    attributes: Attributes


class DedupMatch(BaseModel):
    slug: str
    score: float
    reason: str


class DedupResponse(BaseModel):
    matches: list[DedupMatch] = []


class GenerateSheetRequest(BaseModel):
    slug: str
