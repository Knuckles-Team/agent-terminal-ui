"""Regressions for CI wiring, not a receipt for the installed PTY matrix."""

import hashlib
import importlib.metadata as metadata
import json
import os
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

import agent_terminal_ui
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def startup_step() -> dict[str, Any]:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["native-checks"]["steps"]
    return next(step for step in steps if step.get("name") == "Required installed startup matrix")


def test_startup_ci_reuses_checkout_binary_and_locked_environment() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    job = workflow["jobs"]["native-checks"]
    steps = job["steps"]
    step = startup_step()
    preceding = steps[:steps.index(step)]
    assert any("cargo +1.96.0 build --locked" in item.get("run", "") for item in preceding)
    pty_step = next(item for item in preceding if item.get("name") == "Required compiled-native PTY journeys")
    assert step["env"]["TUI_NATIVE_TEST_BINARY"] == pty_step["env"]["TUI_NATIVE_TEST_BINARY"]
    assert step["env"]["TUI_TEST_INSTALLED_ENV"] == "${{ github.workspace }}/.venv"
    command = step["run"]
    assert "uv build --wheel" in command
    assert "--no-deps --reinstall" in command
    assert "git diff --exit-code" in command
    assert command.index('cd "$RUNNER_TEMP"') < command.index('/bin/python" -I - <<')
    assert '/bin/python" -m pytest "$GITHUB_WORKSPACE/tests/test_entry_environment_pty.py"' in command
    assert "uv sync" not in command and "uv run" not in command
    assert "cargo " not in command
    assert not step.get("continue-on-error") and not job.get("continue-on-error")
    retained = next(item for item in steps if item.get("name") == "Retain installed startup receipts")
    assert retained["if"] == "always()"
    assert "installed-startup-provenance.json" in retained["with"]["path"]
    assert "installed-startup-results.xml" in retained["with"]["path"]


@pytest.mark.parametrize("fault", [None, "file", "metadata", "origin", "editable", "outside-import"])
def test_isolated_provenance_probe_rejects_wrong_installation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str | None
) -> None:
    environment = tmp_path / "environment"
    package = environment / "agent_terminal_ui"
    package.mkdir(parents=True)
    module = package / "__init__.py"
    module.write_text("__version__ = '0.0.0'\n")
    info = environment / "agent_terminal_ui-0.0.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Name: agent-terminal-ui\nVersion: 0.0.0\n")
    (info / "entry_points.txt").write_text("[console_scripts]\nagent-terminal-ui = agent_terminal_ui.terminal_ui:terminal_ui\n")
    wheel = tmp_path / "agent_terminal_ui-0.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path in (module, info / "METADATA", info / "entry_points.txt"):
            archive.write(path, str(path.relative_to(environment)))
    origin: dict[str, Any] = {"url": wheel.as_uri(), "archive_info": {}}
    if fault == "origin":
        origin["url"] = (tmp_path / "other.whl").as_uri()
    if fault == "editable":
        origin["dir_info"] = {"editable": True}
    (info / "direct_url.json").write_text(json.dumps(origin))
    if fault == "file":
        module.write_text("modified = True\n")
    if fault == "metadata":
        (info / "METADATA").write_text("Name: agent-terminal-ui\nVersion: 0.0.1\n")
    imported = tmp_path / "source/__init__.py" if fault == "outside-import" else module
    monkeypatch.setattr(agent_terminal_ui, "__file__", str(imported))
    distribution = metadata.PathDistribution(info)
    monkeypatch.setattr(metadata, "distribution", lambda _name: distribution)
    binary = tmp_path / "agent-terminal-ui-native"
    binary.write_bytes(b"fixture executable")
    binary.chmod(0o700)
    receipt = tmp_path / "provenance.json"
    for key, value in {
        "TUI_TEST_INSTALLED_ENV": str(environment),
        "TUI_TEST_WHEEL": str(wheel),
        "TUI_NATIVE_TEST_BINARY": str(binary),
        "TUI_TEST_SOURCE_REVISION": "source-fixture",
        "TUI_TEST_SOURCE_TREE": "tree-fixture",
        "STARTUP_PROVENANCE": str(receipt),
    }.items():
        monkeypatch.setenv(key, value)
    probe = startup_step()["run"].split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    if fault:
        with pytest.raises(AssertionError):
            exec(compile(probe, "installed-provenance", "exec"), {})
        assert not receipt.exists()
    else:
        exec(compile(probe, "installed-provenance", "exec"), {})
        result = json.loads(receipt.read_text())
        assert result["source_revision"] == "source-fixture"
        assert result["source_tree"] == "tree-fixture"
        assert result["wheel_sha256"] == hashlib.sha256(wheel.read_bytes()).hexdigest()
        assert result["native_sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()
        assert result["verified_wheel_members"] == 3


@pytest.mark.parametrize("fault", [None, "skipped", "failure", "error", "missing"])
def test_startup_junit_gate_requires_all_cases(tmp_path: Path, fault: str | None) -> None:
    suite = ET.Element("testsuite")
    ET.SubElement(suite, "testcase", name="test_log_open_probe_detects_a_counterexample")
    for number in range(17 if fault == "missing" else 18):
        case = ET.SubElement(suite, "testcase", name=f"test_installed_startup_theme_and_log_refusal[{number}]")
        if number == 0 and fault in {"skipped", "failure", "error"}:
            ET.SubElement(case, fault)
    result = tmp_path / "results.xml"
    ET.ElementTree(suite).write(result)
    command = startup_step()["run"].splitlines()[-1]
    code = shlex.split(command)[-1]
    probe = subprocess.run(
        [sys.executable, "-I", "-c", code],
        env={**os.environ, "STARTUP_RESULTS": str(result)},
        cwd=tmp_path, capture_output=True, text=True, timeout=10,
    )
    assert (probe.returncode == 0) is (fault is None), probe.stderr
