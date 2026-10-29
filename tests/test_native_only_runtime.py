"""Keep developer Python separate from the single native runtime."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.spec("TUIG-RUNTIME-R012.1.3.1")
def test_no_live_python_frontend():
    assert not (ROOT / "agent_terminal_ui").exists()
    assert (ROOT / "native/agent-terminal-ui/src/main.rs").is_file()
    assert (ROOT / "LICENSE").is_file()
