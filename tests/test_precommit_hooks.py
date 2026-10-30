import json
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]


@pytest.mark.spec("TUIG-RUNTIME-R006")
def test_pipelines_hook_sections():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    hooks = data["tool"]["pipelines_hooks"]
    assert "public_surface" in hooks
    assert "specs" in hooks["ste"]["paths"]


@pytest.mark.spec("TUIG-RUNTIME-R004.1")
def test_spec_group_preserves_stages():
    data = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
    shared = next(
        repo
        for repo in data["repos"]
        if repo["repo"] == "https://github.com/Knuckles-Team/pipelines"
    )
    hooks = {hook["id"]: hook for hook in shared["hooks"]}
    assert set(hooks["spec"]["stages"]) == {"pre-commit", "pre-push", "manual"}
    assert not hooks["spec"].get("args")
    assert not {"spec-standard", "spec-status", "spec-decomposition"} & hooks.keys()
    assert "secrets" in hooks
    assert not {"spec-trailers", "ste-staged", "stubs", "sprawl"} & hooks.keys()


def test_ci_setup_uses_the_selected_python():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    inputs = workflow["jobs"]["gates"]["with"]
    selected = inputs["python-version"]
    assert f"uv sync --python {selected} " in inputs["setup-command"]


def test_pytest_hook_uses_uv_run_flags_supported_by_the_runner():
    data = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
    hook = next(
        item
        for repo in data["repos"]
        if repo["repo"] == "local"
        for item in repo["hooks"]
        if item["id"] == "pytest"
    )
    entry = hook["entry"]
    assert "uv run --frozen --group test pytest" in entry
    assert "--no-install-project" not in entry


@pytest.mark.spec("TUIG-RUNTIME-R004.2")
def test_layout_and_surface_checks_follow_shared_advisory_policy():
    data = yaml.safe_load((ROOT / ".github/workflows/advisory.yml").read_text())
    # YAML 1.1 loads the Actions `on` key as True.
    triggers = data.get("on", data.get(True))
    assert triggers["schedule"]
    assert "workflow_dispatch" in triggers
    assert data["permissions"] == {"contents": "read"}
    job = data["jobs"]["advisory"]
    assert (
        job["uses"]
        == "Knuckles-Team/pipelines/.github/workflows/advisory_pipeline.yml@main"
    )
    assert set(job["with"]["gates"].split()) == {
        "public-surface",
        "root-hygiene",
        "gitignore-convergence",
    }


@pytest.mark.spec("TUIG-RUNTIME-R004.2")
def test_docs_only_pull_requests_run_the_spec_gate_in_the_shared_job():
    workflows = ROOT / ".github/workflows"
    assert not (workflows / "ci-skip.yml").exists()
    data = yaml.safe_load((workflows / "ci.yml").read_text())
    triggers = data.get("on", data.get(True))
    assert triggers["pull_request"] == {"branches": ["main"]}
    job = data["jobs"]["gates"]
    assert (
        job["uses"]
        == "Knuckles-Team/pipelines/.github/workflows/gates_pipeline.yml@main"
    )
    assert job["if"] == "github.event_name == 'pull_request'"
    assert job["with"]["docs-only-paths"].split() == [
        "specs/*",
        "docs/*",
        "*.md",
        "plans/*",
        "LICENSE",
    ]
    assert "spec" not in job["with"]["skip-hooks"].split(",")


def test_ci_required_aggregates_every_blocking_job_and_skips_native_on_prs():
    data = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    jobs = data["jobs"]
    required = jobs["ci-required"]
    assert required["name"] == "CI required"
    assert required["if"] == "always()"
    assert set(required["needs"]) == {
        "gates",
        "main-gates",
        "full",
        "native-wheels",
        "native-checks",
    }
    assert "ste-advisory" not in required["needs"]
    assert jobs["native-wheels"]["if"] == "github.event_name != 'pull_request'"
    assert jobs["full"]["with"]["backward-python"] == "3.12"
    release = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    assert "pull_request" not in release.get("on", release.get(True))


@pytest.mark.spec("TUIG-RUNTIME-R004.1")
@pytest.mark.parametrize(
    ("ancestor", "retained"),
    [
        ("TUIG-RUNTIME-R008", "TUIG-RUNTIME-R008.3.2"),
        ("TUIG-RUNTIME-R008.2", "TUIG-RUNTIME-R008.2.3.2.2.2.2.2.2"),
        ("TUIG-RUNTIME-R008.3", "TUIG-RUNTIME-R008.3.2"),
        ("TUIG-RUNTIME-R010", "TUIG-RUNTIME-R010.12.2"),
        ("TUIG-RUNTIME-R010", "TUIG-RUNTIME-R010.14"),
        ("TUIG-RUNTIME-R010.12", "TUIG-RUNTIME-R010.12.2"),
    ],
)
def test_bounded_completion_keeps_unqualified_ancestor_acceptance_open(
    ancestor: str, retained: str
) -> None:
    """Current acceptance boundaries must change only with broader proof."""
    status = json.loads((ROOT / "specs/terminal-runtime/status.json").read_text())
    rows = {row["id"]: row for row in status["requirements"]}
    assert rows[ancestor]["delivery_state"] == "SPECIFIED", ancestor
    assert retained in rows, f"Missing retained acceptance: {retained}"
    assert rows[retained]["delivery_state"] == "SPECIFIED", retained
    descendants = set()
    pending = list(rows[ancestor].get("rollup_of", []))
    while pending:
        identifier = pending.pop()
        if identifier not in descendants:
            descendants.add(identifier)
            pending.extend(rows[identifier].get("rollup_of", []))
    assert retained in descendants, f"{ancestor} lost its retained acceptance"


@pytest.mark.spec("TUIG-RUNTIME-R004.1")
def test_ledger_preserves_actual_bounded_native_qualification() -> None:
    status = json.loads((ROOT / "specs/terminal-runtime/status.json").read_text())
    rows = {row["id"]: row for row in status["requirements"]}
    assert {"TUIG-RUNTIME-R010.12.1", "TUIG-RUNTIME-R010.12.2"} <= set(
        rows["TUIG-RUNTIME-R010.12"]["rollup_of"]
    )
    for identifier in (
        "TUIG-RUNTIME-R008.3.1",
        "TUIG-RUNTIME-R008.4.1",
        "TUIG-RUNTIME-R008.4.2",
        "TUIG-RUNTIME-R010.12.1",
        "TUIG-RUNTIME-R010.12.1.1",
        "TUIG-RUNTIME-R010.12.1.2",
    ):
        row = rows[identifier]
        assert row["delivery_state"] == "VERIFIED", identifier
        assert row["landed_in"] and row["verified_by"], identifier
