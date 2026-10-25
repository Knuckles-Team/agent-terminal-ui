"""Verify the installed binary against its wheel, without a runtime launcher."""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from email.parser import BytesParser
from pathlib import Path


def wheel_binary(wheel: Path) -> bytes:
    """Reject a Python launcher, extra executable, or runtime dependency."""
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        scripts = [name for name in names if ".data/scripts/" in name]
        if len(scripts) != 1 or not scripts[0].endswith(".data/scripts/tuig"):
            raise ValueError("wheel must contain exactly one executable: tuig")
        if any(name.endswith((".py", ".pyc", ".pyd")) for name in names):
            raise ValueError("wheel must not ship a Python runtime or launcher")
        metadata_paths = [
            name for name in names if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_paths) != 1:
            raise ValueError("wheel must contain exactly one distribution")
        metadata = BytesParser().parsebytes(archive.read(metadata_paths[0]))
        if metadata["Name"] != "agent-terminal-ui" or metadata.get_all("Requires-Dist"):
            raise ValueError("unexpected distribution name or runtime dependencies")
        binary = archive.read(scripts[0])
        if not binary.startswith(b"\x7fELF"):
            raise ValueError("supported Linux wheel must contain an ELF executable")
        return binary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("executable", type=Path)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    binary = wheel_binary(args.wheel)
    executable = args.executable.resolve(strict=True)
    if executable.read_bytes() != binary or not os.access(executable, os.X_OK):
        raise ValueError("installed executable differs from the wheel")
    with tempfile.TemporaryDirectory() as directory:
        result = subprocess.run(
            [str(executable), "--help"],
            env={"PATH": directory, "HOME": directory, "TERM": "dumb"},
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    if "tuig" not in result.stdout:
        raise ValueError("installed executable does not identify as tuig")
    root = Path(__file__).resolve().parents[1]
    receipt = {
        "source_revision": os.environ["TUI_TEST_SOURCE_REVISION"],
        "source_tree": os.environ["TUI_TEST_SOURCE_TREE"],
        "wheel": args.wheel.name,
        "wheel_sha256": hashlib.sha256(args.wheel.read_bytes()).hexdigest(),
        "native_sha256": hashlib.sha256(binary).hexdigest(),
        "cargo_lock_sha256": hashlib.sha256(
            (root / "native/agent-terminal-ui/Cargo.lock").read_bytes()
        ).hexdigest(),
        "installed_executable": str(executable),
        "empty_path_help": "passed",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
