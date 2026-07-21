import copy
import json

from app.config import WORKFLOWS_DIR
from app.safety import REALISM_NEGATIVE_PROMPT, ANGLE_PHRASES

_DESCRIBE_TEMPLATE = json.loads((WORKFLOWS_DIR / "qwen-sheet-describe.json").read_text())
_REFERENCE_TEMPLATE = json.loads((WORKFLOWS_DIR / "qwen-sheet-edit.json").read_text())


def build_describe_graph(identity_string: str, angle: str, seed: int, count: int) -> dict:
    graph = copy.deepcopy(_DESCRIBE_TEMPLATE)
    phrase = ANGLE_PHRASES[angle]
    graph["5"]["inputs"]["text"] = (
        f"{identity_string}, {phrase}, plain neutral underwear, "
        f"plain seamless background, candid realism, visible pores, "
        f"ordinary face, flat available light"
    )
    graph["6"]["inputs"]["text"] = REALISM_NEGATIVE_PROMPT
    graph["8"]["inputs"]["seed"] = seed
    graph["7"]["inputs"]["batch_size"] = count
    graph["11"]["inputs"]["filename_prefix"] = f"sheet_{angle}"
    return graph


def _likeness_to_denoise(likeness: float) -> float:
    # likeness 1.0 (hug reference) -> denoise 0.3; likeness 0.0 (fresh face) -> denoise 1.0
    return round(1.0 - 0.7 * likeness, 4)


def build_reference_graph(
    ref_image_path: str, angle: str, seed: int, count: int, likeness: float
) -> dict:
    """Build a Qwen-Image-Edit reference graph (identity-preserving).

    The reference image is injected both as in-context conditioning (node 5/6's
    TextEncodeQwenImageEdit ``image`` input) and as the KSampler init latent
    (VAEEncode -> RepeatLatentBatch, node 12/7); ``likeness`` maps to the
    denoise strength at node 8, which controls how tightly the output hugs the
    reference (verified live against ComfyUI).
    """
    graph = copy.deepcopy(_REFERENCE_TEMPLATE)
    phrase = ANGLE_PHRASES[angle]
    graph["2"]["inputs"]["image"] = ref_image_path
    graph["5"]["inputs"]["prompt"] = (
        f"{phrase}, plain neutral underwear, plain seamless background, "
        f"candid realism, visible pores, ordinary face, flat available light"
    )
    graph["6"]["inputs"]["prompt"] = REALISM_NEGATIVE_PROMPT
    graph["8"]["inputs"]["seed"] = seed
    graph["8"]["inputs"]["denoise"] = _likeness_to_denoise(likeness)
    graph["7"]["inputs"]["amount"] = count
    graph["11"]["inputs"]["filename_prefix"] = f"sheet_ref_{angle}"
    return graph
