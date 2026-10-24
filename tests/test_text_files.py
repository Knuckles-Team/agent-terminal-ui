"""Local text-file staging through the real command and application boundary."""

import asyncio
import base64
import json
import os
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from agent_terminal_ui.app import AgentApp
from agent_terminal_ui.client import AgentClient

pytestmark = pytest.mark.spec("TUI-RUNTIME-R012.5.2")


@pytest.fixture
def file_app():
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(400, json={
            "jsonrpc": "2.0", "id": 1,
            "error": {"code": -32602, "message": "fixture refused"},
        })

    client = AgentClient(base_url="http://localhost:8000")
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    client._streaming = True
    app = AgentApp(client=client)
    app.notify = MagicMock()
    app._current_session_id = "context-one"
    return app, requests


@pytest.mark.asyncio
async def test_file_stages_exact_bytes_until_prompt_and_appears_in_help(file_app, tmp_path):
    app, requests = file_app
    path = tmp_path / "résumé notes.txt"
    content = "\ufeffhéllo\r\n\x00world\n".encode()
    path.write_bytes(content)

    assert await app._cmd_processor.process(f'/file "{path}"')

    assert requests == []
    assert app._pending_parts == [{"kind": "file", "file": {
        "bytes": base64.b64encode(content).decode(),
        "mimeType": "text/plain", "name": path.name,
    }}]
    assert path.name in app.notify.call_args.args[0]
    before = list(app._pending_parts)
    await app._cmd_processor.process("/file")
    assert path.name in app.notify.call_args.args[0]
    assert app._pending_parts == before
    conv = MagicMock()
    conv.add_info = AsyncMock()
    app.query_one = MagicMock(return_value=conv)
    await app._cmd_processor.process("/help")
    assert "/file" in conv.add_info.call_args.args[0]
    assert requests == []

    parts = app._collect_pending_parts("read this")
    assert app._pending_parts == []
    events = [event async for event in app._client.stream("read this", parts=parts)]
    assert events[-1]["message"] == "fixture refused"
    sent = json.loads(requests[0].content)["params"]["message"]["parts"]
    assert sent == [{"kind": "text", "text": "read this"}, *before]
    await app._client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [b"", b"\xff", b"x" * 65537])
async def test_file_refuses_invalid_content_without_mutating_staged_parts(file_app, tmp_path, content):
    app, requests = file_app
    app._pending_parts = [{"text": "existing"}]
    path = tmp_path / "bad.txt"
    path.write_bytes(content)

    await app._cmd_processor.process(f"/file {path}")

    assert app._pending_parts == [{"text": "existing"}]
    assert app.notify.call_args.kwargs["severity"] in {"warning", "error"}
    assert requests == []
    await app._client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("path_kind", ["fifo", "directory", "symlink", "missing"])
async def test_file_refuses_non_regular_paths_without_blocking(file_app, tmp_path, path_kind):
    app, requests = file_app
    path = tmp_path / "not-a-file"
    if path_kind == "fifo":
        os.mkfifo(path)
    elif path_kind == "directory":
        path.mkdir()
    elif path_kind == "symlink":
        target = tmp_path / "target.txt"
        target.write_text("valid")
        path.symlink_to(target)

    await asyncio.wait_for(app._cmd_processor.process(f"/file {path}"), timeout=1)

    assert app._pending_parts == []
    assert requests == []
    await app._client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("args", ['"unterminated', "https://example.test/a.txt", "one.txt two.txt"])
async def test_file_refuses_non_path_input_before_read(file_app, monkeypatch, args):
    app, requests = file_app
    opened = MagicMock(side_effect=AssertionError("must not open"))
    monkeypatch.setattr(os, "open", opened)

    await app._cmd_processor.process(f"/file {args}")

    opened.assert_not_called()
    assert app._pending_parts == []
    assert requests == []
    await app._client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("size,count", [(8192, 8), (1, 8), (32769, 1)])
async def test_file_count_and_aggregate_bytes_preserve_prior_valid_parts(file_app, tmp_path, size, count):
    app, requests = file_app
    path = tmp_path / "notes.txt"
    path.write_bytes(b"x" * size)
    for _ in range(count):
        await app._cmd_processor.process(f"/file {path}")
    assert len(app._pending_parts) == count
    before = list(app._pending_parts)

    await app._cmd_processor.process(f"/file {path}")

    assert app._pending_parts == before
    assert requests == []
    await app._client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["/file --clear", "/clear", "interrupt"])
async def test_removal_and_cancel_clear_staged_files(file_app, tmp_path, command):
    app, requests = file_app
    path = tmp_path / "notes.txt"
    path.write_text("notes")
    await app._cmd_processor.process(f"/file {path}")
    app._pending_parts.insert(0, {"text": "existing"})
    conv = MagicMock()
    conv.clear_conversation = AsyncMock()
    app.query_one = MagicMock(return_value=conv)
    app._get_main_screen = MagicMock(return_value=None)
    app._is_processing = True

    if command == "interrupt":
        conv.selection.is_empty = True
        app.action_interrupt()
    else:
        await app._cmd_processor.process(command)

    assert app._pending_parts == [{"text": "existing"}]
    assert requests == []
    await app._client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["client", "context"])
async def test_changed_owner_refuses_pending_submission(file_app, tmp_path, change):
    app, requests = file_app
    original = app._client
    path = tmp_path / "notes.txt"
    path.write_text("private notes")
    await app._cmd_processor.process(f"/file {path}")
    if change == "context":
        app._current_session_id = "other-context"
    else:
        app._client = MagicMock()
    app._run_agent_turn = MagicMock()

    await app._submit_new_message("read this")

    app._run_agent_turn.assert_not_called()
    assert app._pending_parts == []
    assert requests == []
    await original.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["client", "context"])
async def test_queued_files_do_not_combine_and_refuse_owner_change(file_app, tmp_path, change):
    app, requests = file_app
    original = app._client
    path = tmp_path / "notes.txt"
    path.write_text("private notes")
    await app._cmd_processor.process(f"/file {path}")
    app._add_to_queue("old plain message")
    app.query_one = MagicMock()
    app._notify_conversation = AsyncMock()
    await app._handle_queued_submission("read this")
    assert len(app._user_message_queue) == 2
    item = app._user_message_queue[-1]
    assert item["parts"]
    if change == "context":
        app._current_session_id = "other-context"
    else:
        app._client = MagicMock()
    app.post_message = MagicMock()

    worker = app._run_agent_turn
    app._run_agent_turn = MagicMock()
    app._get_main_screen = MagicMock(return_value=None)
    app._user_message_queue = [item]
    app._process_queue()
    assert app._run_agent_turn.call_args.kwargs["attachment_owner"] == item["attachment_owner"]

    await worker.__wrapped__(
        app, item["message"], parts=item["parts"],
        attachment_owner=item["attachment_owner"],
    )

    assert requests == []
    assert app.post_message.call_args.args[0].event["type"] == "error"
    await original.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["clear", "client", "context", "submit"])
async def test_late_file_read_cannot_restore_cleared_or_foreign_input(file_app, monkeypatch, change):
    from agent_terminal_ui import commands

    app, requests = file_app
    original = app._client
    started = asyncio.Event()
    release = asyncio.Event()

    async def delayed(*args):
        started.set()
        await release.wait()
        return {"kind": "file", "file": {
            "bytes": "YQ==", "mimeType": "text/plain", "name": "notes.txt",
        }}

    monkeypatch.setattr(commands.asyncio, "to_thread", delayed)
    staging = asyncio.create_task(app._cmd_processor.process("/file notes.txt"))
    await started.wait()
    if change == "clear":
        await app._cmd_processor.process("/file --clear")
    elif change == "client":
        app._client = MagicMock()
    elif change == "context":
        app._current_session_id = "other-context"
    else:
        assert app._collect_pending_parts("prompt") == []
    release.set()
    await staging

    assert app._pending_parts == []
    assert requests == []
    await original.close()


@pytest.mark.asyncio
async def test_mounted_file_command_and_prompt_use_one_transport_request(file_app, tmp_path):
    from agent_terminal_ui.tui.input_text_area import InputTextArea

    app, requests = file_app
    path = tmp_path / "notes.txt"
    path.write_bytes(b"exact\r\nbytes\n")
    async with app.run_test(size=(120, 35)) as pilot:
        await app.workers.wait_for_complete()
        requests.clear()
        composer = app.screen.query_one(InputTextArea)
        composer.load_text(f"/file {path}")
        composer.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert requests == []
        assert app._pending_parts[0]["file"]["name"] == "notes.txt"

        composer.load_text("read this")
        composer.focus()
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        sent = [request for request in requests if request.url.path == "/a2a"]
        assert len(sent) == 1
        parts = json.loads(sent[0].content)["params"]["message"]["parts"]
        assert parts == [{"kind": "text", "text": "read this"}, {
            "kind": "file", "file": {
                "bytes": base64.b64encode(path.read_bytes()).decode(),
                "mimeType": "text/plain", "name": "notes.txt",
            },
        }]
        assert app._pending_parts == []
        assert not app._is_processing
    await app._client.close()


@pytest.mark.asyncio
async def test_filename_markup_is_literal_in_stage_list_and_error(file_app, tmp_path):
    app, requests = file_app
    path = tmp_path / "[red]notes.txt"
    path.write_text("notes")

    await app._cmd_processor.process(f'/file "{path}"')
    assert app._pending_parts[0]["file"]["name"] == "[red]notes.txt"
    assert "\\[red]notes.txt" in app.notify.call_args.args[0]
    await app._cmd_processor.process("/file")
    assert "\\[red]notes.txt" in app.notify.call_args.args[0]
    await app._cmd_processor.process(f'/file "{tmp_path / "[red]missing.txt"}"')
    assert "\\[red]missing.txt" in app.notify.call_args.args[0]
    assert len(app._pending_parts) == 1
    assert requests == []
    await app._client.close()
