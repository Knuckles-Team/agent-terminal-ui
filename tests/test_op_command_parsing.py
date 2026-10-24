"""Operation command parsing rejects malformed input before client dispatch."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_terminal_ui.commands import CommandProcessor


@pytest.fixture
def command_app():
    app = MagicMock()
    app.agent_client.invoke_op = AsyncMock(return_value={"ok": True})
    app.query_one.return_value.add_info = AsyncMock()
    return app


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.1")
@pytest.mark.parametrize("separator", [" ", "  ", "\t", "\n", "\r\n"])
async def test_op_preserves_json_values_after_whitespace(command_app, separator):
    processor = CommandProcessor(command_app)
    assert await processor.process(
        '/op query.uql' + separator + '{"text":"RETURN 1", "params":{"label":"a b\\tc"}}'
    )
    command_app.agent_client.invoke_op.assert_awaited_once_with(
        "query.uql", {"text": "RETURN 1", "params": {"label": "a b\tc"}}
    )
    command_app.notify.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.1")
@pytest.mark.parametrize(
    "raw",
    [
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":-Infinity}',
        '{"params":{"nested":[NaN]}}',
        '{"value":',
        '{"value":1} trailing',
        '[1,2]',
        'null',
    ],
)
async def test_op_invalid_json_never_reaches_client_and_next_command_works(command_app, raw):
    processor = CommandProcessor(command_app)
    assert await processor.process('/op query.uql ' + raw)
    command_app.agent_client.invoke_op.assert_not_awaited()
    command_app.notify.assert_called_once()
    assert command_app.notify.call_args.kwargs == {"severity": "warning"}
    assert not processor._pending_op_plans
    command_app.query_one.return_value.add_info.assert_not_awaited()

    await processor.process('/op query.uql {"text":"NaN Infinity -Infinity", "params":{}}')
    command_app.agent_client.invoke_op.assert_awaited_once_with(
        "query.uql", {"text": "NaN Infinity -Infinity", "params": {}}
    )


@pytest.mark.asyncio
@pytest.mark.spec("TUI-RUNTIME-R001.1")
async def test_op_missing_id_refuses_and_omitted_object_remains_empty(command_app):
    processor = CommandProcessor(command_app)
    await processor.process('/op')
    command_app.agent_client.invoke_op.assert_not_awaited()
    await processor.process('/op fleet.status')
    command_app.agent_client.invoke_op.assert_awaited_once_with('fleet.status', {})
