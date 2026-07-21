import json
import shutil
from pathlib import Path

from app.schema import Card

ANGLE_ORDER = ["front", "34", "profile", "body"]


def card_dir(models_root: Path, slug: str) -> Path:
    return models_root / slug


def _card_md(card: Card) -> str:
    lines = [
        f"# {card.name} (`{card.slug}`)",
        "",
        f"- gender: {card.gender}",
        f"- status: {card.status}",
        f"- seed: {card.seed}",
        f"- provenance: {card.provenance}",
        f"- created: {card.created}",
        "",
        "## Identity string",
        "",
        card.identity_string,
        "",
        "## Attributes",
        "",
    ]
    for field, value in card.attributes.model_dump().items():
        if value:
            lines.append(f"- {field}: {value}")
    return "\n".join(lines) + "\n"


def write_card(models_root: Path, card: Card) -> None:
    d = card_dir(models_root, card.slug)
    d.mkdir(parents=True, exist_ok=True)
    (d / "card.json").write_text(json.dumps(card.model_dump(), indent=2))
    (d / "card.md").write_text(_card_md(card))


def read_card(models_root: Path, slug: str) -> Card:
    d = card_dir(models_root, slug)
    data = json.loads((d / "card.json").read_text())
    return Card(**data)


def list_cards(models_root: Path) -> list[Card]:
    if not models_root.exists():
        return []
    cards = []
    for d in sorted(models_root.iterdir()):
        if d.is_dir() and (d / "card.json").exists():
            cards.append(read_card(models_root, d.name))
    return cards


def copy_reference_frames(
    models_root: Path, slug: str, picked: dict[str, str], source_dir: Path
) -> list[str]:
    dest_dir = card_dir(models_root, slug) / "reference"
    dest_dir.mkdir(parents=True, exist_ok=True)
    written = []
    angle_filenames = {"front": "front.png", "34": "34.png",
                        "profile": "profile.png", "body": "body.png"}
    for angle in ANGLE_ORDER:
        src = source_dir / picked[angle]
        dest_name = angle_filenames[angle]
        dest = dest_dir / dest_name
        shutil.copyfile(src, dest)
        written.append(f"reference/{dest_name}")
    return written
