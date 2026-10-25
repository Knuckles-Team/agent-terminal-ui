"""Native wheel contract; these checks do not qualify a compiled artifact."""

import importlib.util
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_native_wheel", ROOT / "scripts/verify_native_wheel.py"
)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class NativePackagingTests(unittest.TestCase):
    @pytest.mark.spec("TUI-RUNTIME-R015.31")
    def test_binary_only_metadata(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertEqual(project["project"]["name"], "tuig")
        self.assertEqual(project["project"]["version"], "2.3.3")
        self.assertEqual(project["project"]["dependencies"], [])
        self.assertNotIn("scripts", project["project"])
        self.assertEqual(project["tool"]["maturin"]["bindings"], "bin")
        self.assertTrue(project["tool"]["maturin"]["locked"])
        cargo = tomllib.loads(
            (ROOT / "native/agent-terminal-ui/Cargo.toml").read_text()
        )
        self.assertEqual([item["name"] for item in cargo["bin"]], ["tuig"])

    def test_rejects_python_launcher_and_dependencies(self):
        for extra, dependencies, executable in [
            ("", "", b"\x7fELFfixture"),
            ("agent_terminal_ui/__init__.py", "", b"\x7fELFfixture"),
            ("", "Requires-Dist: textual\n", b"\x7fELFfixture"),
            ("", "", b"#!/usr/bin/python\n"),
        ]:
            with self.subTest(
                extra=extra, dependencies=dependencies, executable=executable
            ):
                with tempfile.TemporaryDirectory() as directory:
                    wheel = Path(directory) / "fixture.whl"
                    with zipfile.ZipFile(wheel, "w") as archive:
                        archive.writestr(
                            "tuig-2.3.3.data/scripts/tuig", executable
                        )
                        archive.writestr(
                            "tuig-2.3.3.dist-info/METADATA",
                            "Name: tuig\n" + dependencies,
                        )
                        if extra:
                            archive.writestr(extra, "")
                    if extra or dependencies or not executable.startswith(b"\x7fELF"):
                        with self.assertRaises(ValueError):
                            VERIFIER.wheel_binary(wheel)
                    else:
                        self.assertEqual(VERIFIER.wheel_binary(wheel), executable)
