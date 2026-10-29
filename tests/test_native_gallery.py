"""The gallery is a reproducible cell rendering of the real native program."""

import hashlib
import json
import os
from pathlib import Path
from xml.etree import ElementTree

import pyte
import pytest

from scripts.capture_native_gallery import capture, terminal_svg


@pytest.mark.spec("TUIG-RUNTIME-R008.3")
def test_svg_preserves_cells_colors_inverse_and_escapes():
    screen = pyte.Screen(3, 1)
    pyte.Stream(screen).feed("\x1b[38;2;17;34;51m\x1b[48;2;68;85;102m<&\x1b[7mX")
    svg = terminal_svg(screen, "Map <fixture>")
    root = ElementTree.fromstring(svg)
    ns = {"s": "http://www.w3.org/2000/svg"}
    texts = root.findall(".//s:text", ns)
    assert [node.text for node in texts] == ["<", "&", "X"]
    assert texts[0].attrib["fill"] == "#112233"
    assert texts[2].attrib["fill"] == "#445566"
    assert root.findall(".//s:rect", ns)[-1].attrib["fill"] == "#112233"
    assert root.attrib["viewBox"] == "0 0 27 18"
    pyte.Stream(screen).feed("\r\x1b[31mR")
    with pytest.raises(ValueError, match="requires truecolor cells"):
        terminal_svg(screen, "Unsupported ANSI color")


@pytest.mark.spec("TUIG-RUNTIME-R008.3")
def test_committed_gallery_has_matching_provenance_and_safe_svg():
    root = Path(__file__).parents[1]
    assets = root / "docs/assets/native"
    manifest = json.loads((assets / "manifest.json").read_text())
    assert manifest["synthetic"] is True
    assert len(manifest["screens"]) == 6
    for name, digest in manifest["fixtures"].items():
        assert (
            hashlib.sha256((root / "tests/fixtures" / name).read_bytes()).hexdigest()
            == digest
        )
    for screen in manifest["screens"]:
        raw = (assets / screen["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == screen["sha256"]
        svg = ElementTree.fromstring(raw)
        assert "synthetic fixture" in "".join(svg.itertext())
        assert all(
            node.tag.rsplit("}", 1)[-1] in {"svg", "title", "desc", "g", "rect", "text"}
            for node in svg.iter()
        )
        for node in svg.iter():
            assert not any(
                key.startswith("on") or key.endswith("href") for key in node.attrib
            )


@pytest.mark.spec("TUIG-RUNTIME-R008.3", "TUIG-RUNTIME-R010.12.1")
@pytest.mark.skipif(
    not os.environ.get("TUI_NATIVE_TEST_BINARY"),
    reason="Requires compiled native binary",
)
def test_actual_native_gallery_capture(tmp_path):
    receipt = capture(Path(os.environ["TUI_NATIVE_TEST_BINARY"]), tmp_path, "0" * 40)
    assert len(receipt["screens"]) == 6
    assert any(
        request["path"] == "/api/v1/ops/runs.execution_graph"
        for request in receipt["requests"]
    )
