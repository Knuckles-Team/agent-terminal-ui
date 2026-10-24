"""Source-owned environment inventory and real dynamic settings behavior."""

import ast
import re
from pathlib import Path

import pytest

from agent_terminal_ui.settings import AppSettings, SETTINGS_SCHEMA

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.spec("TUI-RUNTIME-R015.41.2")


def source_inputs(extra_python: str = "", extra_rust: str = "") -> set[str]:
    names: set[str] = set()
    sources = [(str(path), path.read_text()) for path in (ROOT / "agent_terminal_ui").rglob("*.py")]
    sources.append(("counterexample.py", extra_python))
    for path, source in sources:
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and ast.unparse(node.func) in {"os.getenv", "os.environ.get"}:
                value = node.args[0]
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    names.add(value.value)
                else:
                    assert path.endswith("settings.py")
                    assert ast.unparse(value) in {"key", "key.upper()"}
            if isinstance(node, ast.Subscript) and ast.unparse(node.value) == "os.environ":
                assert isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str)
                names.add(node.slice.value)
    rust = extra_rust + "\n".join(path.read_text() for path in (ROOT / "native/agent-terminal-ui/src").rglob("*.rs"))
    names.update(re.findall(r'env::var(?:_os)?\("([A-Z_]+)"\)', rust))
    return names


def check_inventory(document: str, extra_python: str = "", extra_rust: str = "") -> None:
    documented = set(re.findall(r"^\| `([A-Z_]+)` \|", document, re.MULTILINE))
    assert source_inputs(extra_python, extra_rust) <= documented
    aliases = set(re.findall(r"^\| `([a-z_]+)` \| `([A-Z_]+)` \|$", document, re.MULTILINE))
    assert aliases == {(setting.key, setting.key.upper()) for setting in SETTINGS_SCHEMA}
    for phrase in ["empty lowercase value falls through", "empty uppercase value is still an override",
                   "Invalid integers remain strings", "String environment overrides remain literal",
                   "not startup aliases", "does not override that factory"]:
        assert phrase in document


def test_all_source_inputs_and_schema_aliases_are_documented() -> None:
    check_inventory((ROOT / "docs/configuration.md").read_text())


@pytest.mark.parametrize("source,rust", [
    ('import os\nos.getenv("UNDOCUMENTED_SETTING")', ""),
    ('import os\nos.environ["UNDOCUMENTED_SETTING"]', ""),
    ("", 'env::var("UNDOCUMENTED_SETTING")'),
])
def test_inventory_rejects_new_undocumented_reads(source: str, rust: str) -> None:
    with pytest.raises(AssertionError):
        check_inventory((ROOT / "docs/configuration.md").read_text(), source, rust)


@pytest.mark.parametrize("old,new", [
    ("`TERM_PROGRAM`", "`MISSING_TERM_PROGRAM`"),
    ("`MAX_LOG_LINES`", "`MISSING_MAX_LOG_LINES`"),
    ("Invalid integers remain strings", "Invalid integers always raise"),
])
def test_inventory_rejects_missing_aliases_and_wrong_semantics(old: str, new: str) -> None:
    document = (ROOT / "docs/configuration.md").read_text()
    assert old in document
    with pytest.raises(AssertionError):
        check_inventory(document.replace(old, new))


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppSettings:
    monkeypatch.setenv("AGENT_UTILITIES_CONFIG_DIR", str(tmp_path / "global"))
    for setting in SETTINGS_SCHEMA:
        monkeypatch.delenv(setting.key, raising=False)
        monkeypatch.delenv(setting.key.upper(), raising=False)
    return AppSettings(tmp_path / "settings.toml")


@pytest.mark.parametrize("key,kind", [(setting.key, setting.type) for setting in SETTINGS_SCHEMA])
def test_every_schema_key_supports_uppercase_override(settings: AppSettings, monkeypatch: pytest.MonkeyPatch, key: str, kind: str) -> None:
    raw, expected = ("YES", True) if kind == "boolean" else ("17", 17) if kind == "integer" else ("override-value", "override-value")
    monkeypatch.setenv(key.upper(), raw)
    assert settings.get(key) == expected


@pytest.mark.parametrize("lower,upper,expected", [
    ("lower", "upper", "lower"), ("", "upper", "upper"),
    (None, "", ""), ("", None, "stored"), (None, None, "stored"),
])
def test_exact_case_and_empty_value_precedence(settings: AppSettings, monkeypatch: pytest.MonkeyPatch, lower: str | None, upper: str | None, expected: str) -> None:
    settings.set("shell_command", "stored")
    for key, value in [("shell_command", lower), ("SHELL_COMMAND", upper)]:
        if value is not None:
            monkeypatch.setenv(key, value)
    monkeypatch.setenv("Shell_Command", "mixed-case")
    assert settings.get("shell_command") == expected


@pytest.mark.parametrize("value,expected", [("on", True), ("TrUe", True), ("1", True), ("no", False), ("garbage", False), ("", False)])
def test_boolean_coercion_is_explicit(settings: AppSettings, monkeypatch: pytest.MonkeyPatch, value: str, expected: bool) -> None:
    monkeypatch.setenv("SHOW_TOKENS", value)
    assert settings.get("show_tokens") is expected


def test_invalid_integer_and_expansion_boundaries(settings: AppSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_LOG_LINES", "invalid")
    assert settings.get("max_log_lines") == "invalid"
    monkeypatch.setenv("TUI_TEST_EXPANSION", "expanded")
    settings.set("shell_command", "$TUI_TEST_EXPANSION/${TUI_TEST_EXPANSION}")
    assert settings.get("shell_command") == "expanded/expanded"
    assert settings.get("shell_command", expand=False) == "$TUI_TEST_EXPANSION/${TUI_TEST_EXPANSION}"
    monkeypatch.setenv("SHELL_COMMAND", "$TUI_TEST_EXPANSION")
    assert settings.get("shell_command") == "$TUI_TEST_EXPANSION"
    monkeypatch.setenv("UNREGISTERED_KEY", "raw")
    assert settings.get("unregistered_key") == "raw"


def test_environment_local_global_and_schema_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    monkeypatch.setenv("AGENT_UTILITIES_CONFIG_DIR", str(global_dir))
    monkeypatch.delenv("shell_command", raising=False)
    monkeypatch.delenv("SHELL_COMMAND", raising=False)
    local = tmp_path / "settings.toml"
    assert AppSettings(local).get("shell_command") == ""
    (global_dir / "config.json").write_text('{"shell_command": "global"}')
    assert AppSettings(local).get("shell_command") == "global"
    local.write_text('shell_command = "local"\n')
    configured = AppSettings(local)
    assert configured.get("shell_command") == "local"
    monkeypatch.setenv("SHELL_COMMAND", "environment")
    assert configured.get("shell_command") == "environment"
    monkeypatch.delenv("SHELL_COMMAND")
    assert configured.get("shell_command") == "local"
