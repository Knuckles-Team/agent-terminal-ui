"""Published theme and log behavior must distinguish the two entry points."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.spec("TUI-RUNTIME-R015.42.2")


def check_entry_environment_documentation(document: str) -> None:
    source = (ROOT / "native/agent-terminal-ui/src/presentation.rs").read_text()
    declaration = re.search(r"const THEMES:[^=]+=(\s*\[.*?\]);", source)
    assert declaration is not None
    themes = json.loads(declaration.group(1))
    listed = document.split("Native themes: ", 1)[1].splitlines()[0]
    assert re.findall(r"`([^`]+)`", listed) == themes
    for text in (
        "Startup theme for Python and native", "Both use `tokyo-night` when AGENT_THEME is unset or unknown",
        "NO_COLOR disables Python colors when present, including an empty value",
        "Native colors are disabled only when NO_COLOR is nonempty",
        "`AGENT_LOG_FILE` | ignored", "never open the given local path",
        "Python `/logs` and Ctrl+V require an authenticated host reader",
        "Native `l` opens the host-log view and also requires authenticated host access",
    ):
        assert text in document


def test_published_theme_and_log_entry_contracts() -> None:
    check_entry_environment_documentation((ROOT / "docs/configuration.md").read_text())


@pytest.mark.parametrize("old,new", [
    ("Startup theme for Python and native", "Startup Textual theme"),
    ("`nord`, `gruvbox`", "`gruvbox`"),
    ("unset or unknown", "unset only"),
    ("including an empty value", "excluding an empty value"),
    ("NO_COLOR is nonempty", "NO_COLOR is present"),
    ("`AGENT_LOG_FILE` | ignored", "`AGENT_LOG_FILE` | opened"),
    ("never open the given local path", "read the local path"),
])
def test_documentation_rejects_incorrect_entry_behavior(old: str, new: str) -> None:
    document = (ROOT / "docs/configuration.md").read_text()
    assert old in document
    with pytest.raises(AssertionError):
        check_entry_environment_documentation(document.replace(old, new))
