import copy
import json

from app.config import WORKFLOWS_DIR
from app.safety import REALISM_NEGATIVE_PROMPT, ANGLE_PHRASES

_DESCRIBE_TEMPLATE = json.loads((WORKFLOWS_DIR / "qwen-sheet-describe.json").read_text())


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
