from pathlib import Path

import pytest

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
    for heading in ["Commands", "Quality gates", "Branching & isolation", "Documentation"]:
        assert f"## {heading}" in text
