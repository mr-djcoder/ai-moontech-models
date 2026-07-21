from pathlib import Path
import pytest
from app.schema import Attributes, Card, PickedFrame
from app import models_store


def make_card(slug="jess"):
    return Card(
        slug=slug, name="Jess", gender="female", status="card",
        identity_string="a synthetic woman, late 20s, ...", seed=48120,
        attributes=Attributes(age_band="late 20s"),
        reference_images=[f"reference/front.png", f"reference/34.png",
                           f"reference/profile.png", f"reference/body.png"],
        provenance="synthetic", release=None, created="2026-07-21",
    )


def test_write_then_read_card(tmp_path):
    card = make_card()
    models_store.write_card(tmp_path, card)
    loaded = models_store.read_card(tmp_path, "jess")
    assert loaded == card
    assert (tmp_path / "jess" / "card.json").exists()
    assert (tmp_path / "jess" / "card.md").exists()


def test_list_cards_empty(tmp_path):
    assert models_store.list_cards(tmp_path) == []


def test_list_cards_returns_all(tmp_path):
    models_store.write_card(tmp_path, make_card("jess"))
    models_store.write_card(tmp_path, make_card("steven"))
    slugs = sorted(c.slug for c in models_store.list_cards(tmp_path))
    assert slugs == ["jess", "steven"]


def test_copy_reference_frames(tmp_path):
    source_dir = tmp_path / "jobs" / "job123"
    source_dir.mkdir(parents=True)
    for name in ["front_0.png", "34_0.png", "profile_0.png", "body_0.png"]:
        (source_dir / name).write_bytes(b"fake-png-bytes")
    picked = {"front": PickedFrame(filename="front_0.png"),
              "34": PickedFrame(filename="34_0.png"),
              "profile": PickedFrame(filename="profile_0.png"),
              "body": PickedFrame(filename="body_0.png")}
    result = models_store.copy_reference_frames(tmp_path, "jess", picked, source_dir)
    assert sorted(result) == sorted([
        "reference/front.png", "reference/34.png",
        "reference/profile.png", "reference/body.png",
    ])
    for rel in result:
        assert (tmp_path / "jess" / rel).exists()


def test_copy_reference_frames_resolves_subfolder(tmp_path):
    # ComfyUI wrote candidate PNGs into a non-empty subfolder; the picked
    # entries carry that subfolder and must not be silently dropped.
    source_dir = tmp_path / "output"
    sub = source_dir / "job123"
    sub.mkdir(parents=True)
    for name in ["front_0.png", "34_0.png", "profile_0.png", "body_0.png"]:
        (sub / name).write_bytes(b"fake-png-bytes")
    picked = {"front": PickedFrame(filename="front_0.png", subfolder="job123"),
              "34": PickedFrame(filename="34_0.png", subfolder="job123"),
              "profile": PickedFrame(filename="profile_0.png", subfolder="job123"),
              "body": PickedFrame(filename="body_0.png", subfolder="job123")}
    result = models_store.copy_reference_frames(tmp_path, "jess", picked, source_dir)
    assert sorted(result) == sorted([
        "reference/front.png", "reference/34.png",
        "reference/profile.png", "reference/body.png",
    ])
    for rel in result:
        assert (tmp_path / "jess" / rel).exists()


def test_copy_reference_frames_missing_file_raises(tmp_path):
    source_dir = tmp_path / "output"
    source_dir.mkdir(parents=True)
    # Only three of the four picked files actually exist on disk.
    for name in ["front_0.png", "34_0.png", "profile_0.png"]:
        (source_dir / name).write_bytes(b"fake-png-bytes")
    picked = {"front": PickedFrame(filename="front_0.png"),
              "34": PickedFrame(filename="34_0.png"),
              "profile": PickedFrame(filename="profile_0.png"),
              "body": PickedFrame(filename="missing_0.png")}
    with pytest.raises(FileNotFoundError):
        models_store.copy_reference_frames(tmp_path, "jess", picked, source_dir)
