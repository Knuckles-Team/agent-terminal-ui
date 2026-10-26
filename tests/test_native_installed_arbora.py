"""Pair the installed native candidate with Arbora's real boot lifecycle.

The provider and PTY harness use separate hash-locked environments. The rejected
bearer uses a fresh terminal; this does not prove same-process stale clearing.
"""

import asyncio
import importlib
import os
import re
import secrets
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest


def native_context_id() -> str:
    """Generate the public A2A context shape, not a display label."""
    return "a2a-context-" + secrets.token_hex(32)


def submit_with_context(
    submit: Callable[..., Any], context_id: str
) -> Callable[..., Any]:
    """Add a real A2A context to the pinned fixture's durable admission input."""

    def admitted(*args: Any, **kwargs: Any) -> Any:
        metadata = kwargs["metadata"]
        assert metadata["a2a_schema"] == "arbora-a2a-unary-v1"
        assert metadata["a2a_owner_ref"]
        assert metadata["a2a_run_id"] == kwargs["run_id"]
        assert "a2a_context_id" not in metadata
        assert context_id and context_id != kwargs["run_id"]
        return submit(
            *args,
            **{**kwargs, "metadata": {**metadata, "a2a_context_id": context_id}},
        )

    return admitted


@pytest.mark.spec("TUI-RUNTIME-R010.8")
@pytest.mark.skipif(
    not os.environ.get("TUI_PTY_PYTHON"),
    reason="Requires the isolated installed-provider qualification job",
)
def test_installed_native_reads_real_admitted_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boot = importlib.import_module("test_real_boot")
    work_items = importlib.import_module("arbora.work_items")
    original = boot._check_served_native_reads
    context_id = native_context_id()
    models = importlib.import_module("arbora.a2a.models")
    models.A2ATask.model_validate(
        {
            "id": "work-item:" + "0" * 64,
            "contextId": context_id,
            "status": {"state": "working"},
        }
    )
    # The immutable provider fixture omits context metadata because its own
    # operation reads do not use A2A. Supply it before the real durable submit;
    # never alter the served task response, registry or authority readers.
    monkeypatch.setattr(
        work_items,
        "submit_work_item_atomic",
        submit_with_context(work_items.submit_work_item_atomic, context_id),
    )

    async def paired_reads(stack: dict[str, Any], run_id: str, item_id: str) -> None:
        await original(stack, run_id, item_id)
        environment = {
            **os.environ,
            "TUI_SERVED_TEST_URL": stack["base_url"],
            "TUI_SERVED_TEST_BEARER": stack["token"],
            "TUI_SERVED_TEST_TASK_ID": item_id,
            "TUI_SERVED_TEST_RUN_ID": run_id,
            "TUI_SERVED_TEST_CONTEXT_ID": context_id,
            "TUI_SERVED_TEST_PLAN_TEXT": "[in_progress] inspect",
        }
        result = await asyncio.to_thread(
            subprocess.run,
            [
                os.environ["TUI_PTY_PYTHON"],
                "-I",
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "-q",
                "-rA",
                "--junitxml=" + os.environ["TUI_PAIRED_PTY_RESULTS"],
                "tests/test_native_served_reads_pty.py::test_installed_arbora_current_plan_read_and_refusal",
            ],
            cwd=Path(os.environ["TUI_PTY_ROOT"]),
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    monkeypatch.setattr(boot, "_check_served_native_reads", paired_reads)
    boot.test_native_current_plan_lifecycle_uses_installed_engine(monkeypatch)


@pytest.mark.spec("TUI-RUNTIME-R010.8")
def test_context_admission_delegates_without_replacing_the_provider() -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    engine = object()
    metadata = {
        "a2a_schema": "arbora-a2a-unary-v1",
        "a2a_owner_ref": "owner-ref",
        "a2a_run_id": "native-run",
    }
    params = {"run_id": "native-run", "metadata": metadata, "queue": "native-queue"}

    def submit(*args: Any, **kwargs: Any) -> tuple[str, bool]:
        calls.append((args, kwargs))
        return "work-item:distinct-owner", True

    result = submit_with_context(submit, "distinct-context")(engine, **params)
    assert result == ("work-item:distinct-owner", True)
    assert calls == [
        (
            (engine,),
            {
                **params,
                "metadata": {**metadata, "a2a_context_id": "distinct-context"},
            },
        )
    ]
    assert "a2a_context_id" not in metadata


@pytest.mark.spec("TUI-RUNTIME-R010.8")
def test_native_context_id_matches_the_public_a2a_contract() -> None:
    contexts = [native_context_id(), native_context_id()]
    assert contexts[0] != contexts[1]
    assert all(re.fullmatch(r"a2a-context-[0-9a-f]{64}", value) for value in contexts)
