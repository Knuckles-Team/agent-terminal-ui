"""Preserve archived analysis in Git, outside release version mirrors."""

import configparser
import hashlib
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REVISION = "17e010c140395735bef41dba5a896ea0000ac99e"
ARCHIVE = "plans/spec-source-history/analysis"
REPORTS = [
    pytest.param(
        "results.json",
        "28ecaab72f6eedf75d3df249e5f05052dfb05472a32d36dc987e49dcd506521f",
        marks=pytest.mark.spec("TUIG-RUNTIME-R015.32"),
    ),
    pytest.param(
        "code_enhancement_report.md",
        "2ba4a62a4333f2dc616e7b1315e5a28e982ba224db4929489a3acac1a22074f6",
        marks=pytest.mark.spec("TUIG-RUNTIME-R015.33"),
    ),
]


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        timeout=10,
        check=False,
        env=environment,
    )


def _historical_report(repository: Path, filename: str) -> bytes:
    if not (repository / ".git").exists():
        pytest.skip("History qualification needs a Git checkout, not a source export")
    result = _git(repository, "show", f"{REVISION}:{ARCHIVE}/{filename}")
    if result.returncode:
        shallow = _git(repository, "rev-parse", "--is-shallow-repository")
        if shallow.returncode == 0 and shallow.stdout.strip() == b"true":
            pytest.skip("History qualification needs full Git history; use fetch --unshallow")
    assert result.returncode == 0, "The full checkout must retain the archived report"
    return result.stdout


def _assert_preserved(content: bytes, digest: str) -> None:
    assert hashlib.sha256(content).hexdigest() == digest


def _assert_not_a_version_mirror(configuration: str, filename: str) -> None:
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(configuration)
    targets = [
        section.removeprefix("bumpversion:file:")
        for section in config.sections()
        if section.startswith("bumpversion:file:")
    ]
    assert all(Path(target).name != filename for target in targets)


@pytest.mark.parametrize("filename,digest", REPORTS)
def test_historical_report_preserves_original_bytes(filename: str, digest: str) -> None:
    _assert_preserved(_historical_report(ROOT, filename), digest)


@pytest.mark.parametrize("filename,digest", REPORTS)
def test_historical_report_rejects_changed_bytes(filename: str, digest: str) -> None:
    original = _historical_report(ROOT, filename)
    with pytest.raises(AssertionError):
        _assert_preserved(original + b"changed", digest)


@pytest.mark.parametrize("filename,digest", REPORTS)
def test_historical_report_is_not_a_current_version_mirror(filename: str, digest: str) -> None:
    _assert_not_a_version_mirror((ROOT / ".bumpversion.cfg").read_text(), filename)
    for directory in (".specify/reports", ARCHIVE):
        assert not (ROOT / directory / filename).exists()


@pytest.mark.parametrize("filename,digest", REPORTS)
@pytest.mark.parametrize("directory", [".specify/reports", ARCHIVE])
def test_historical_report_rejects_release_rewriting(filename: str, digest: str, directory: str) -> None:
    config = (ROOT / ".bumpversion.cfg").read_text()
    config += f"\n[bumpversion:file:{directory}/{filename}]\n"
    with pytest.raises(AssertionError):
        _assert_not_a_version_mirror(config, filename)


@pytest.mark.spec("TUIG-RUNTIME-R015.32", "TUIG-RUNTIME-R015.33")
def test_source_export_does_not_claim_history_qualification(tmp_path: Path) -> None:
    with pytest.raises(pytest.skip.Exception, match="not a source export"):
        _historical_report(tmp_path, "results.json")


@pytest.mark.spec("TUIG-RUNTIME-R015.32", "TUIG-RUNTIME-R015.33")
def test_shallow_history_is_unqualified_but_missing_full_history_fails(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    assert _git(source, "init", "--quiet").returncode == 0
    commit = _git(
        source, "-c", "user.name=History fixture", "-c", "user.email=fixture@example.test",
        "-c", "commit.gpgsign=false", "commit", "--quiet", "--allow-empty", "-m", "Fixture",
    )
    assert commit.returncode == 0, commit.stderr
    with pytest.raises(AssertionError, match="must retain the archived report"):
        _historical_report(source, "results.json")
    shallow = tmp_path / "shallow"
    clone = _git(tmp_path, "clone", "--quiet", "--depth=1", source.as_uri(), str(shallow))
    assert clone.returncode == 0, clone.stderr
    with pytest.raises(pytest.skip.Exception, match="needs full Git history"):
        _historical_report(shallow, "results.json")
