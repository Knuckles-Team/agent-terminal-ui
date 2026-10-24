"""Execute the configured client lint/type hooks, including real refusals."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.spec("TUI-RUNTIME-R015.48")


@pytest.fixture
def gate_repository(tmp_path: Path) -> tuple[Path, str]:
    runner = os.environ.get("TUI_TEST_PRE_COMMIT")
    if not runner:
        pytest.skip("Set TUI_TEST_PRE_COMMIT to the installed qualification runner")
    assert runner is not None
    assert Path(runner).is_file() and os.access(runner, os.X_OK)
    cache = os.environ.get("PRE_COMMIT_HOME")
    assert cache and (Path(cache) / "db.db").is_file(), "Reuse the populated hook cache"
    for name in (".pre-commit-config.yaml", "pyproject.toml"):
        (tmp_path / name).write_bytes((ROOT / name).read_bytes())
    package = tmp_path / "agent_terminal_ui"
    package.mkdir()
    (package / "client.py").write_text("def caller_id() -> str:\n    return \"caller\"\n")
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "add", "agent_terminal_ui/client.py"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path, runner


@pytest.mark.parametrize("hook,invalid,diagnostic", [
    ("ruff", 'def caller_id() -> str:\n    return unknown_caller\n', "F821"),
    ("mypy", 'def caller_id() -> str:\n    return 7\n', "return-value"),
])
def test_configured_client_hook_accepts_valid_input_and_rejects_wrong_result(
    gate_repository: tuple[Path, str], hook: str, invalid: str, diagnostic: str,
) -> None:
    root, runner = gate_repository
    command = [runner, "run", hook, "--config", ".pre-commit-config.yaml", "--all-files", "--hook-stage", "pre-commit"]
    clean = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=60)
    output = clean.stdout + clean.stderr
    assert clean.returncode == 0, output
    assert "Passed" in output and "Skipped" not in output, output
    assert "Installing environment" not in output, output
    (root / "agent_terminal_ui/client.py").write_text(invalid)
    rejected = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=60)
    output = rejected.stdout + rejected.stderr
    assert rejected.returncode != 0, output
    assert "Failed" in output and diagnostic in output, output
    assert "Skipped" not in output, output
