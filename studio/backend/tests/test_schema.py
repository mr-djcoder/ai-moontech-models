import pytest
from pydantic import ValidationError
from app.schema import Attributes, Candidate, Card, GenerateRequest, SaveRequest


def test_card_roundtrip():
    card = Card(
        slug="jess",
        name="Jess",
        gender="female",
        status="card",
        identity_string="a synthetic woman, late 20s, ...",
        seed=48120,
        attributes=Attributes(age_band="late 20s"),
        base_wardrobe="plain neutral underwear set",
        reference_images=["reference/front.png", "reference/34.png",
                           "reference/profile.png", "reference/body.png"],
        provenance="synthetic",
        release=None,
        created="2026-07-21",
    )
    dumped = card.model_dump()
    assert dumped["slug"] == "jess"
    assert dumped["status"] == "card"
    assert Card(**dumped) == card


def test_card_status_rejects_invalid():
    with pytest.raises(ValidationError):
        Card(
            slug="x", name="X", gender="female", status="not-a-status",
            identity_string="s", seed=1, attributes=Attributes(age_band="30s"),
            base_wardrobe="plain neutral underwear set", reference_images=[],
            provenance="synthetic", release=None, created="2026-07-21",
        )


def test_generate_request_modes():
    req = GenerateRequest(mode="describe", attributes=Attributes(age_band="30s"), count=8)
    assert req.mode == "describe"
    with pytest.raises(ValidationError):
        GenerateRequest(mode="not-a-mode", count=8)


def test_candidate_carries_filename_and_subfolder():
    cand = Candidate(
        url="http://comfy/view?filename=front_0.png&subfolder=job1&type=output",
        filename="front_0.png", subfolder="job1", angle="front", index=0,
    )
    assert cand.filename == "front_0.png"
    assert cand.subfolder == "job1"


def test_candidate_subfolder_defaults_empty():
    cand = Candidate(
        url="http://comfy/view?filename=front_0.png&subfolder=&type=output",
        filename="front_0.png", angle="front", index=0,
    )
    assert cand.subfolder == ""


def test_save_request_requires_picked():
    req = SaveRequest(
        slug="jess", name="Jess", gender="female",
        identity_string="s", seed=1, attributes=Attributes(age_band="30s"),
        provenance="synthetic", release=None,
        picked={"front": {"filename": "front_0.png", "subfolder": "job123"},
                "34": {"filename": "34_0.png", "subfolder": "job123"},
                "profile": {"filename": "profile_0.png", "subfolder": "job123"},
                "body": {"filename": "body_0.png", "subfolder": "job123"}},
    )
    assert req.picked["front"].filename == "front_0.png"
    assert req.picked["front"].subfolder == "job123"


def test_save_request_picked_subfolder_optional():
    req = SaveRequest(
        slug="jess", name="Jess", gender="female",
        identity_string="s", seed=1, attributes=Attributes(age_band="30s"),
        provenance="synthetic", release=None,
        picked={"front": {"filename": "front_0.png"},
                "34": {"filename": "34_0.png"},
                "profile": {"filename": "profile_0.png"},
                "body": {"filename": "body_0.png"}},
    )
    assert req.picked["front"].subfolder == ""
