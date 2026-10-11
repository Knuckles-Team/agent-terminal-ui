import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.mark.spec("TUI-RUNTIME-R006")
def test_pipelines_hook_sections():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    hooks = data["tool"]["pipelines_hooks"]
    assert "public_surface" in hooks
    assert "specs" in hooks["ste"]["paths"]
