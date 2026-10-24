"""License provenance and configured authoritative Python version mirrors."""

import configparser
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def check_license(project: dict, license_text: str, tracked: set[str]) -> None:
    assert project["license"]["text"] == "MIT"
    assert "agent_terminal_ui/LICENSE" in tracked
    package_data = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["package-data"]
    assert "LICENSE" in package_data["agent_terminal_ui"]
    assert "Copyright" in license_text
    assert "Permission is hereby granted, free of charge" in license_text
    assert "THE SOFTWARE IS PROVIDED" in license_text
    assert "[MIT License](agent_terminal_ui/LICENSE)" in (ROOT / "README.md").read_text()


@pytest.mark.spec("TUI-RUNTIME-R015.18")
def test_declared_mit_license_is_tracked_and_linked() -> None:
    tracked = set(subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    check_license(project, (ROOT / "agent_terminal_ui/LICENSE").read_text(), tracked)


@pytest.mark.spec("TUI-RUNTIME-R015.18")
@pytest.mark.parametrize("mutation", ["missing", "empty", "different"])
def test_license_rejects_missing_or_mismatched_declaration(mutation: str) -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    license_text = (ROOT / "agent_terminal_ui/LICENSE").read_text()
    tracked = {"agent_terminal_ui/LICENSE"}
    if mutation == "missing":
        tracked.clear()
    elif mutation == "empty":
        license_text = ""
    else:
        project["license"]["text"] = "Apache-2.0"
    with pytest.raises(AssertionError):
        check_license(project, license_text, tracked)


def check_version_mirrors(configuration: str, contents: dict[str, str]) -> None:
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(configuration)
    version = config["bumpversion"]["current_version"]
    configured = {section.removeprefix("bumpversion:file:") for section in config.sections() if section.startswith("bumpversion:file:")}
    assert configured == contents.keys()
    for path, content in contents.items():
        search = config[f"bumpversion:file:{path}"]["search"].format(current_version=version)
        assert content.count(search) == 1, path
    assert tomllib.loads(contents["pyproject.toml"])["project"]["version"] == version
    packages = tomllib.loads(contents["uv.lock"])["package"]
    assert next(p["version"] for p in packages if p["name"] == "agent-terminal-ui") == version


def test_python_version_mirrors_are_registered() -> None:
    check_version_mirrors((ROOT / ".bumpversion.cfg").read_text(), {
        path: (ROOT / path).read_text() for path in ("pyproject.toml", "docs/concepts.md", "uv.lock")
    })


@pytest.mark.parametrize("path", ["pyproject.toml", "docs/concepts.md", "uv.lock"])
def test_version_mirrors_reject_drift_and_unregistered_files(path: str) -> None:
    configuration = (ROOT / ".bumpversion.cfg").read_text()
    contents = {p: (ROOT / p).read_text() for p in ("pyproject.toml", "docs/concepts.md", "uv.lock")}
    with pytest.raises(AssertionError):
        check_version_mirrors(configuration.replace(f"bumpversion:file:{path}", f"bumpversion:file:missing/{path}"), contents)
    config = configparser.ConfigParser()
    config.read_string(configuration)
    contents[path] = contents[path].replace(config["bumpversion"]["current_version"], "0.0.0")
    with pytest.raises(AssertionError):
        check_version_mirrors(configuration, contents)


def check_native_version_mirror(manifest: str, lock: str) -> None:
    package = tomllib.loads(manifest)["package"]
    assert package["publish"] is False
    packages = tomllib.loads(lock)["package"]
    matching = [item for item in packages if item["name"] == package["name"]]
    assert len(matching) == 1
    assert matching[0]["version"] == package["version"]


def test_native_manifest_and_lock_agree() -> None:
    check_native_version_mirror((ROOT / "native/agent-terminal-ui/Cargo.toml").read_text(),
                                (ROOT / "native/agent-terminal-ui/Cargo.lock").read_text())


@pytest.mark.parametrize("mutation", ["version", "name"])
def test_native_version_mirror_rejects_drift(mutation: str) -> None:
    manifest = (ROOT / "native/agent-terminal-ui/Cargo.toml").read_text()
    lock = (ROOT / "native/agent-terminal-ui/Cargo.lock").read_text()
    value = tomllib.loads(manifest)["package"][mutation]
    with pytest.raises(AssertionError):
        check_native_version_mirror(manifest, lock.replace(value, "missing-mirror", 1))
