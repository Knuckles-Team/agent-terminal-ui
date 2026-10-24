"""Documentation captures use the actual app, never personal state or services."""

from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

import pytest

from scripts.capture_screenshots import CAPTURES, capture_screenshots, update_assets


@pytest.mark.spec("TUI-RUNTIME-R016")
async def test_demo_captures_are_repeatable_and_isolated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AGENT_BEARER_TOKEN", "private-token-sentinel")
    monkeypatch.setenv("AGENT_UTILITIES_CONFIG_DIR", str(tmp_path))
    private_config = tmp_path / "config.json"
    private_config.write_text('{"theme": "private-theme-sentinel"}')
    with patch("httpx.AsyncClient.send", side_effect=AssertionError("Network access")):
        first = await capture_screenshots()
        second = await capture_screenshots()
    assert first == second
    assert first.keys() == CAPTURES.keys()
    for filename, svg in first.items():
        root = ElementTree.fromstring(svg)
        text = " ".join(root.itertext()).replace("\u00a0", " ")
        assert root.tag.endswith("svg")
        assert "Synthetic documentation demo" in text
        assert "private-token-sentinel" not in svg
        assert "private-theme-sentinel" not in svg
        assert str(tmp_path) not in svg
        assert (
            "Settings" in text if filename.startswith("settings") else "parser" in text
        )
    assert private_config.read_text() == '{"theme": "private-theme-sentinel"}'
    assert first["chat-wide.svg"] != first["chat-compact.svg"]


@pytest.mark.spec("TUI-RUNTIME-R016")
def test_freshness_check_is_read_only(tmp_path: Path) -> None:
    output = tmp_path / "screenshots"
    assets = {"demo.svg": "<svg>demo</svg>\n"}
    assert update_assets(assets, output, check=True) == ["demo.svg"]
    assert not output.exists()
    assert update_assets(assets, output, check=False) == ["demo.svg"]
    assert update_assets(assets, output, check=True) == []
    (output / "demo.svg").write_text("stale")
    assert update_assets(assets, output, check=True) == ["demo.svg"]
    assert (output / "demo.svg").read_text() == "stale"
