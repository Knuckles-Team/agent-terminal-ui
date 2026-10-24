"""The production shared pytest fixture must isolate and restore settings state."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.spec("TUI-RUNTIME-R015.37")


def test_shared_fixture_isolates_settings_and_restores_environment(tmp_path: Path) -> None:
    suite = tmp_path / "suite"
    suite.mkdir()
    home = tmp_path / "home"
    local = home / ".config/agent-terminal-ui/settings.toml"
    local.parent.mkdir(parents=True)
    local.write_text('shell_command = "developer-local"\n')
    global_dir = tmp_path / "developer-config"
    global_dir.mkdir()
    global_config = global_dir / "config.json"
    global_config.write_text('{"shell_command": "developer-global"}')
    conftest = (ROOT / "tests/conftest.py").read_text()
    conftest += '''

from agent_terminal_ui import settings as settings_module
_original_file = settings_module.DEFAULT_SETTINGS_FILE
_original_config = os.environ.get("AGENT_UTILITIES_CONFIG_DIR")
_original_data = os.environ.get("AGENT_UTILITIES_DATA_DIR")

def pytest_sessionfinish(session, exitstatus):
    assert settings_module.DEFAULT_SETTINGS_FILE == _original_file
    assert os.environ.get("AGENT_UTILITIES_CONFIG_DIR") == _original_config
    assert os.environ.get("AGENT_UTILITIES_DATA_DIR") == _original_data
'''
    (suite / "conftest.py").write_text(conftest)
    (suite / "test_probe.py").write_text('''
from pathlib import Path
import os
import pytest
from agent_terminal_ui.settings import AppSettings
from agent_terminal_ui import settings as settings_module

@pytest.mark.parametrize("iteration", [1, 2])
def test_no_developer_state_or_cross_test_leak(tmp_path, iteration):
    assert settings_module.DEFAULT_SETTINGS_FILE.is_relative_to(tmp_path)
    assert Path(os.environ["AGENT_UTILITIES_CONFIG_DIR"]).is_relative_to(tmp_path)
    assert Path(os.environ["AGENT_UTILITIES_DATA_DIR"]).is_relative_to(tmp_path)
    current = AppSettings()
    assert current.get("shell_command") == ""
    current.set("shell_command", f"test-{iteration}")
    assert AppSettings().get("shell_command") == f"test-{iteration}"
    custom = AppSettings(tmp_path / "explicit.toml")
    custom.set("shell_command", "explicit")
    assert custom.get("shell_command") == "explicit"
    assert AppSettings().get("shell_command") == f"test-{iteration}"
''')
    environment = {**os.environ, "HOME": str(home), "AGENT_UTILITIES_CONFIG_DIR": str(global_dir),
                   "AGENT_UTILITIES_DATA_DIR": str(tmp_path / "developer-data"),
                   "PYTHONPATH": str(ROOT), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    environment.pop("shell_command", None)
    environment.pop("SHELL_COMMAND", None)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(suite), "--confcutdir", str(suite), "-q"],
        cwd=suite, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout
    assert local.read_text() == 'shell_command = "developer-local"\n'
    assert global_config.read_text() == '{"shell_command": "developer-global"}'
    assert not (tmp_path / "developer-data").exists()
