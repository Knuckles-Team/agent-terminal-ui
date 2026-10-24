"""Source/fixture parity only; these checks do not execute the native terminal."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native/agent-terminal-ui"


def fixture():
    return json.loads((NATIVE / "tests/fixtures/execution_graph_contract.json").read_text())


@pytest.mark.spec("TUI-RUNTIME-R010.11")
def test_native_graph_source_limits_match_producer_fixture():
    contract = fixture()
    source = (NATIVE / "src/execution_graph.rs").read_text()
    assert contract["contract_owner"] == "Knuckles-Team/arbora"
    assert contract["operation"] == "runs.execution_graph"
    assert re.fullmatch("[0-9a-f]{40}", contract["source_revision"])
    assert "not released SDK or served-stack acceptance" in contract["source_note"]
    definitions = contract["schema"]["result"]["$defs"]
    properties = definitions["ExecutionGraphSnapshot"]["properties"]
    limits = {
        "MAX_NODES": properties["nodes"]["maxItems"],
        "MAX_EDGES": properties["edges"]["maxItems"],
        "MAX_EVENTS": properties["covered_after"]["maximum"],
        "MAX_KEY_CHARS": definitions["ExecutionStep"]["properties"]["key"]["maxLength"],
    }
    for name, limit in limits.items():
        assert re.search(rf"pub const {name}: (?:usize|u64) = {limit};", source)
    assert limits == {"MAX_NODES": 64, "MAX_EDGES": 2016, "MAX_EVENTS": 1000, "MAX_KEY_CHARS": 16384}
    assert '.read_run_operation(' in source
    assert '"runs.execution_graph"' in source
    assert '.get_run(' not in source
    assert '.http.' not in source


@pytest.mark.spec("TUI-RUNTIME-R010.11")
@pytest.mark.parametrize("field", ["value", "unicode_value", "max_unicode_value"])
def test_native_producer_fixture_preserves_semantic_tuple_and_root_identity(field):
    contract = fixture()
    value = contract[field]
    assert value["schema_version"] == "arbora-execution-graph-v1"
    assert value["availability"] == "available"
    assert 0 < len(value["run_id"]) <= 512
    assert 0 < len(value["task_id"]) <= 512
    snapshot = value["snapshot"]
    assert 0 < len(snapshot["nodes"]) <= 64
    assert len(snapshot["edges"]) <= 2016
    identities = set()
    for node in snapshot["nodes"]:
        identity = tuple(json.loads(node["key"]))
        assert identity == (value["run_id"], "plan_step", node["task_id"])
        assert identity not in identities
        identities.add(identity)
        assert 0 < len(node["key"]) <= 16384
    for edge in snapshot["edges"]:
        assert edge["kind"] == "depends_on"
        assert tuple(json.loads(edge["source"])) in identities
        assert tuple(json.loads(edge["target"])) in identities
    for capability in ("can_read_transcript", "can_message_active", "can_continue_completed", "supports_spawned_children"):
        assert snapshot[capability] is False
    if field == "max_unicode_value":
        assert len(value["run_id"]) == 512
        assert len(snapshot["nodes"][0]["task_id"]) == 512
        assert len(snapshot["nodes"][0]["key"]) > 8192
