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


@pytest.mark.spec("TUI-RUNTIME-R004.1")
def test_spec_group_preserves_stages_and_trailer_fallback():
    data = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
    shared = next(repo for repo in data["repos"] if repo["repo"] == "https://github.com/Knuckles-Team/pipelines")
    hooks = {hook["id"]: hook for hook in shared["hooks"]}
    assert set(hooks["spec"]["stages"]) == {"pre-commit", "pre-push", "manual"}
    assert not hooks["spec"].get("args")
    assert not {"spec-standard", "spec-status", "spec-decomposition"} & hooks.keys()
    assert hooks["spec-trailers"]["stages"] == ["pre-push", "manual"]
    assert hooks["spec-trailers"]["args"] == ["--base-ref", "origin/main"]
    assert {"ste-staged", "stubs", "sprawl"} <= hooks.keys()


def test_ci_setup_uses_the_selected_python():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    inputs = workflow["jobs"]["gates"]["with"]
    selected = inputs["python-version"]
    assert f"uv sync --python {selected} " in inputs["setup-command"]
