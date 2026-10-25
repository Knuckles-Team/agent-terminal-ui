from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
PAGES = ["start.md", "status.md", "deployment.md", "design-system.md"]


@pytest.mark.spec("TUI-RUNTIME-R005")
def test_docs_pages_in_nav():
    nav = (ROOT / "mkdocs.yml").read_text()
    for page in PAGES:
        assert (ROOT / "docs" / page).is_file()
        assert page in nav


@pytest.mark.spec("TUI-RUNTIME-R009")
def test_agents_md_headings():
    text = (ROOT / "AGENTS.md").read_text()
    for heading in [
        "Commands",
        "Quality gates",
        "Branching & isolation",
        "Documentation",
    ]:
        assert f"## {heading}" in text


@pytest.mark.spec("TUI-RUNTIME-R007")
def test_release_qualification_uses_native_wheels_without_publication() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    assert workflow["jobs"] == {
        "native-wheels": {"uses": "./.github/workflows/native-wheels.yml"}
    }
    assert workflow["permissions"] == {"contents": "read"}
