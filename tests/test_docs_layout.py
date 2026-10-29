from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
PAGES = ["start.md", "status.md", "deployment.md", "design-system.md"]


@pytest.mark.spec("TUIG-RUNTIME-R005")
def test_docs_pages_in_nav():
    nav = (ROOT / "mkdocs.yml").read_text()
    for page in PAGES:
        assert (ROOT / "docs" / page).is_file()
        assert page in nav


@pytest.mark.spec("TUIG-RUNTIME-R009")
def test_agents_md_headings():
    text = (ROOT / "AGENTS.md").read_text()
    for heading in [
        "Commands",
        "Quality gates",
        "Branching & isolation",
        "Documentation",
    ]:
        assert f"## {heading}" in text


@pytest.mark.spec("TUIG-RUNTIME-R007")
def test_release_publishes_after_native_wheels_on_tags() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
    assert workflow["jobs"]["native-wheels"] == {
        "uses": "./.github/workflows/native-wheels.yml"
    }
    publish = workflow["jobs"]["publish-pypi"]
    assert publish["needs"] == ["native-wheels"]
    assert publish["if"] == "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')"
    assert publish["runs-on"] == "ubuntu-24.04"
    assert publish["permissions"] == {"contents": "write"}
    steps = publish["steps"]
    downloads = [step for step in steps if step.get("uses", "").startswith("actions/download-artifact@")]
    assert {step["with"]["name"] for step in downloads} == {
        "native-wheel-x86_64",
        "native-wheel-aarch64",
    }
    assembly_index = next(
        i for i, step in enumerate(steps) if step.get("name") == "Assemble and verify qualified publication artifacts"
    )
    publish_index = next(
        i for i, step in enumerate(steps) if step.get("uses", "").startswith("pypa/gh-action-pypi-publish@")
    )
    source_index = next(
        i for i, step in enumerate(steps) if step.get("name") == "Verify release source before publication"
    )
    assert assembly_index < source_index < publish_index
    assert "manylinux_2_28" in steps[assembly_index]["run"]
    assert steps[source_index]["env"]["SOURCE_COMMIT"] == "${{ github.sha }}"
    publish = steps[publish_index]
    assert publish["with"]["packages-dir"] == "dist/"
    assert publish["with"]["password"] == "${{ secrets.PYPI_API_TOKEN }}"
    assert not any("python_pipeline.yml" in step.get("uses", "") for step in steps)
    assert workflow["permissions"] == {"contents": "read"}
