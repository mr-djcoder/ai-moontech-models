import json
from pathlib import Path
from app import workflows
from app.config import WORKFLOWS_DIR


def test_build_describe_graph_sets_prompt_and_seed():
    graph = workflows.build_describe_graph(
        identity_string="a synthetic woman, late 20s, athletic build",
        angle="front", seed=48120, count=8,
    )
    assert "front-facing" in graph["5"]["inputs"]["text"]
    assert "a synthetic woman, late 20s, athletic build" in graph["5"]["inputs"]["text"]
    assert graph["8"]["inputs"]["seed"] == 48120
    assert graph["7"]["inputs"]["batch_size"] == 8


def test_build_describe_graph_includes_realism_negative():
    graph = workflows.build_describe_graph(
        identity_string="a synthetic man, 30s", angle="body", seed=1, count=1,
    )
    assert "glossy render" in graph["6"]["inputs"]["text"].lower()


def test_build_describe_graph_uses_correct_angle_phrase():
    for angle, phrase in [("front", "front-facing"), ("34", "three-quarter turn"),
                           ("profile", "full profile"), ("body", "full-body standing")]:
        graph = workflows.build_describe_graph(
            identity_string="a synthetic person", angle=angle, seed=1, count=1,
        )
        assert phrase in graph["5"]["inputs"]["text"]


def test_qwen_sheet_describe_json_exists_and_has_expected_nodes():
    data = json.loads((WORKFLOWS_DIR / "qwen-sheet-describe.json").read_text())
    for node_id in ["5", "6", "7", "8", "11"]:
        assert node_id in data
