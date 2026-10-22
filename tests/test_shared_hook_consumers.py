"""Configuration contracts for the two shared development hook owners."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.spec("TUI-RUNTIME-R015.29.1")

OWNERS = {
    "no-legacy-concepts": ("pipelines", "5f151c60c25212da9ec67c8bbd26de5f5e6c91f4"),
    "lane-guard": ("repository-manager", "09e91390d446950d345304c7a05fb69d86fdca8b"),
}


def _assert_owner(config: dict, hook_id: str) -> None:
    owner, revision = OWNERS[hook_id]
    entries = [(repo, hook) for repo in config["repos"] for hook in repo["hooks"] if hook["id"] == hook_id]
    assert len(entries) == 1
    repo, hook = entries[0]
    assert repo["repo"] == f"https://github.com/Knuckles-Team/{owner}"
    assert repo["rev"] == revision
    assert hook["stages"] == ["pre-commit", "pre-push"]
    assert hook["pass_filenames"] is False
    assert hook["always_run"] is True
    assert "entry" not in hook and "language" not in hook


def _config() -> dict:
    return yaml.safe_load((Path(__file__).parents[1] / ".pre-commit-config.yaml").read_text())


@pytest.mark.parametrize("hook_id", OWNERS)
def test_shared_hook_owner_configuration(hook_id: str) -> None:
    """Pin the canonical owners with a reproducible canonical spec generator."""
    config = _config()
    _assert_owner(config, hook_id)
    policy = next(repo for repo in config["repos"] if any(hook["id"] == "spec" for hook in repo["hooks"]))
    assert policy["rev"] == "a2dd609d494364daf26fdb3b18abbffa10095993"


@pytest.mark.parametrize("hook_id", OWNERS)
@pytest.mark.parametrize("field,value", [("stages", ["manual"]), ("pass_filenames", True), ("always_run", False), ("entry", "retired-script")])
def test_shared_hook_rejects_changed_semantics(hook_id: str, field: str, value: object) -> None:
    config = deepcopy(_config())
    hook = next(hook for repo in config["repos"] for hook in repo["hooks"] if hook["id"] == hook_id)
    hook[field] = value
    with pytest.raises(AssertionError):
        _assert_owner(config, hook_id)


@pytest.mark.parametrize("hook_id", OWNERS)
@pytest.mark.parametrize("field,value", [("repo", "local"), ("rev", "main")])
def test_shared_hook_rejects_unpinned_owner(hook_id: str, field: str, value: str) -> None:
    config = deepcopy(_config())
    repo = next(repo for repo in config["repos"] if any(hook["id"] == hook_id for hook in repo["hooks"]))
    repo[field] = value
    with pytest.raises(AssertionError):
        _assert_owner(config, hook_id)
