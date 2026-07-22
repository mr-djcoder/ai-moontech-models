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
    # Angles cycle fastest, combos cycle after all angles are exhausted.
    for i in range(count):
        angle_idx = i % len(_ANGLES)
        combo_idx = (i // len(_ANGLES)) % len(combos)
        light, dist = combos[combo_idx]
        angle = _ANGLES[angle_idx]
        variants.append(DatasetVariant(
            angle=angle,
            extra=f"{light}, {dist}",
            seed=base_seed + i,
        ))

    return variants


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
