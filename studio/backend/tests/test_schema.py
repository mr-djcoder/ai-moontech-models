import pytest
from pydantic import ValidationError
from app.schema import Attributes, Card, GenerateRequest, SaveRequest


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


def test_save_request_requires_picked():
    req = SaveRequest(
        slug="jess", name="Jess", gender="female",
        identity_string="s", seed=1, attributes=Attributes(age_band="30s"),
        provenance="synthetic", release=None,
        picked={"front": "job123/front_0.png", "34": "job123/34_0.png",
                "profile": "job123/profile_0.png", "body": "job123/body_0.png"},
    )
    assert req.picked["front"] == "job123/front_0.png"
