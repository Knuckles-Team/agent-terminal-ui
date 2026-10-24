"""Keep the owning client contract tied to source and executed evidence."""

import ast
import re
import shlex
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.spec("TUI-RUNTIME-R015.51")
METHODS = {"get_mcp_config", "list_mcp_tools", "list_history_tasks"}
REGRESSIONS = {
    "test_client_maintenance_gates.py", "test_client_read_contracts.py", "test_client.py",
    "test_client_methods.py", "test_served_fleet_usage.py", "test_task_history.py",
    "test_history_refresh.py", "test_history_navigation.py", "test_mounted_command_matrix.py",
    "test_text_files.py",
}


def check_client_maintenance_documentation(document: str) -> None:
    source = ast.parse((ROOT / "agent_terminal_ui/client.py").read_text())
    client = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == "AgentClient")
    mappings: dict[str, str] = {}
    for method in client.body:
        if isinstance(method, ast.AsyncFunctionDef) and method.name in METHODS:
            calls = [node for node in ast.walk(method) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute) and node.args
                     and ast.unparse(node.func) in {"self._rpc", "self._read_operation_value"}]
            assert len(calls) == 1
            operation = calls[0].args[0]
            assert isinstance(operation, ast.Constant) and isinstance(operation.value, str)
            mappings[method.name] = operation.value
    rows = dict(re.findall(r"^\| `AgentClient\.(\w+)` \| (.+) \|$", document, re.MULTILINE))
    assert mappings.keys() == METHODS
    assert METHODS <= rows.keys()
    for method_name, operation_name in mappings.items():
        assert f"`{operation_name}`" in rows[method_name]
    heading = "## Client maintenance qualification (R015.48, R015.51)"
    assert heading in document
    receipt = document.split(heading, 1)[1].split("\n## ", 1)[0]
    assert "The owning implementation is `agent_terminal_ui/client.py`" in receipt
    assert re.search(r"passed \d+ tests without skips in [\d.]+ seconds", receipt)
    commands = re.findall(r"```bash\n([^`]+)```", receipt)
    assert len(commands) == 1
    arguments = shlex.split(commands[0])
    assert arguments[:3] == ["python", "-m", "pytest"]
    assert {Path(arg).name for arg in arguments if arg.startswith("tests/")} == REGRESSIONS
    assert [arg for arg in arguments[3:] if not arg.startswith("tests/")] == ["-q", "-n", "2", "-p", "no:randomly"]
    assert all((ROOT / "tests" / name).is_file() for name in REGRESSIONS)
    assert "prove consumer behavior, not backend authorization enforcement or live producers" in document
    assert "This evidence is not an installed-wheel qualification" in receipt


def test_client_contract_matches_source_and_executed_receipt() -> None:
    check_client_maintenance_documentation((ROOT / "specs/terminal-runtime/test-spec.md").read_text())


@pytest.mark.parametrize("old,new", [
    ("`AgentClient.get_mcp_config`", "`AgentClient.missing_method`"),
    ("`fleet.status` returns caller-visible children", "`fleet.catalog.list` returns caller-visible children"),
    ("The owning implementation is `agent_terminal_ui/client.py`", "The owning implementation is unknown"),
    ("tests/test_client.py tests/test_client_methods.py", "tests/test_client_methods.py"),
    ("python -m pytest tests/test_client_maintenance_gates.py", "echo pytest tests/test_client_maintenance_gates.py"),
    ("tests/test_text_files.py -q -n 2", "tests/test_text_files.py -q -n 2 -k history"),
    ("passed 407 tests without skips in 67.46 seconds", "have an unrecorded outcome"),
    ("not backend authorization enforcement or live producers", "including backend authorization enforcement and live producers"),
])
def test_client_contract_rejects_wrong_mapping_or_evidence(old: str, new: str) -> None:
    document = (ROOT / "specs/terminal-runtime/test-spec.md").read_text()
    assert old in document
    with pytest.raises(AssertionError):
        check_client_maintenance_documentation(document.replace(old, new))
