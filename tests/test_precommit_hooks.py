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


@pytest.mark.spec("TUI-RUNTIME-R004.2")
def test_layout_and_surface_checks_follow_shared_advisory_policy():
    data = yaml.safe_load((ROOT / ".github/workflows/advisory.yml").read_text())
    # YAML 1.1 loads the Actions `on` key as True.
    triggers = data.get("on", data.get(True))
    assert triggers["schedule"]
    assert "workflow_dispatch" in triggers
    assert data["permissions"] == {"contents": "read"}
    job = data["jobs"]["advisory"]
    assert job["uses"] == "Knuckles-Team/pipelines/.github/workflows/advisory_pipeline.yml@main"
    assert set(job["with"]["gates"].split()) == {
        "public-surface", "root-hygiene", "gitignore-convergence"
    }


@pytest.mark.spec("TUI-RUNTIME-R004.2")
def test_docs_ci_enforces_spec_checks_with_full_history_and_range():
    data = yaml.safe_load((ROOT / ".github/workflows/ci-skip.yml").read_text())
    triggers = data.get("on", data.get(True))
    assert "specs/**" in triggers["pull_request"]["paths"]
    job = data["jobs"]["gates"]
    assert not job.get("continue-on-error")
    steps = job["steps"]
    checkout = next(step for step in steps if step.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["fetch-depth"] == 0
    commands = [step for step in steps if "run" in step]
    assert len(commands) == 1
    check = commands[0]
    assert not check.get("continue-on-error")
    assert check["env"]["BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
    assert check["run"] == (
        "uvx --from pre-commit==4.6.2 pre-commit run spec --config .pre-commit-config.yaml "
        '--hook-stage pre-commit --from-ref "$BASE_SHA" --to-ref HEAD'
    )
    assert "SKIP" not in check.get("env", {})
    assert "SKIP" not in job.get("env", {})
