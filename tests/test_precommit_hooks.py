import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]


@pytest.mark.spec("TUI-RUNTIME-R006")
def test_pipelines_hook_sections():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    hooks = data["tool"]["pipelines_hooks"]
    assert "public_surface" in hooks
    assert "specs" in hooks["ste"]["paths"]


def test_ci_setup_uses_the_selected_python():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    inputs = workflow["jobs"]["gates"]["with"]
    selected = inputs["python-version"]
    assert f"uv sync --python {selected} " in inputs["setup-command"]
