"""Bootstrap command contracts without downloads or hook installation."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def bootstrap(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/bootstrap.sh", scripts / "bootstrap.sh")
    (repo / ".python-version").write_text("3.14\n")
    (repo / "uv.lock").write_text("version = 1\n")
    (repo / ".pre-commit-config.yaml").write_text("repos: []\n")
    commands = tmp_path / "bin"
    commands.mkdir()
    log = tmp_path / "commands.log"
    for command, body in {
        "uv": (
            'if [ "$1" = --version ]; then\n'
            'echo "uv ${TEST_UV_VERSION:-0.13.5}"; exit 0; fi\n'
            'printf "uv %s\\n" "$*" >> "$TEST_COMMAND_LOG"\n'
            'if [ "$1" = sync ]; then exit "${TEST_SYNC_EXIT:-0}"; fi\n'
        ),
        "uvx": (
            'printf "uvx %s\\n" "$*" >> "$TEST_COMMAND_LOG"\n'
            'exit "${TEST_HOOK_EXIT:-0}"\n'
        ),
        "python3": 'printf "python3 %s\\n" "$*" >> "$TEST_COMMAND_LOG"\nexit 1\n',
        "curl": 'printf "curl %s\\n" "$*" >> "$TEST_COMMAND_LOG"\nexit 1\n',
    }.items():
        executable = commands / command
        executable.write_text("#!/bin/sh\n" + body)
        executable.chmod(0o755)
    env = {
        "HOME": str(tmp_path / "home"),
        "PATH": os.pathsep.join((str(commands), "/usr/bin", "/bin")),
        "TEST_COMMAND_LOG": str(log),
    }
    return repo, env, log


def run_bootstrap(
    repo: Path, env: dict[str, str], *args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", "scripts/bootstrap.sh", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_bootstrap_uses_locked_python_and_both_hooks_twice(
    bootstrap: tuple[Path, dict[str, str], Path],
) -> None:
    repo, env, log = bootstrap
    for _ in range(2):
        result = run_bootstrap(repo, env)
        assert result.returncode == 0, result.stderr
        assert "Gate command: uvx pre-commit run --all-files" in result.stdout
    assert (
        log.read_text().splitlines()
        == [
            "uv python install 3.14",
            "uv sync --locked --python 3.14",
            "uvx pre-commit install --config .pre-commit-config.yaml "
            "--hook-type pre-commit --hook-type pre-push",
        ]
        * 2
    )


def test_bootstrap_help_from_relative_path_is_read_only(
    bootstrap: tuple[Path, dict[str, str], Path],
) -> None:
    repo, env, log = bootstrap
    result = subprocess.run(
        ["/bin/bash", "repo/scripts/bootstrap.sh", "--help"],
        cwd=repo.parents[0],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "One-command contributor setup" in result.stdout
    assert not log.exists()


def test_bootstrap_installer_failure_never_runs_network_shell(
    bootstrap: tuple[Path, dict[str, str], Path],
) -> None:
    repo, env, log = bootstrap
    env["TEST_UV_VERSION"] = "0.8.0"
    result = run_bootstrap(repo, env)
    assert result.returncode == 2
    assert "https://docs.astral.sh/uv/getting-started/installation/" in result.stderr
    assert log.read_text().splitlines() == [
        "python3 -m pip install --quiet --user --upgrade uv>=0.9",
    ]


@pytest.mark.parametrize("failure", ["TEST_SYNC_EXIT", "TEST_HOOK_EXIT"])
def test_bootstrap_propagates_setup_failure(
    bootstrap: tuple[Path, dict[str, str], Path], failure: str
) -> None:
    repo, env, log = bootstrap
    env[failure] = "7"
    result = run_bootstrap(repo, env)
    assert result.returncode == 7
    assert "done." not in result.stdout
    if failure == "TEST_SYNC_EXIT":
        assert "uvx" not in log.read_text()


def test_bootstrap_rejects_unknown_arguments_without_setup(
    bootstrap: tuple[Path, dict[str, str], Path],
) -> None:
    repo, env, log = bootstrap
    result = run_bootstrap(repo, env, "--unknown")
    assert result.returncode == 2
    assert "unknown argument" in result.stderr
    assert not log.exists()
