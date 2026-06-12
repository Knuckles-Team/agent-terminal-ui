"""Regression-guard contract tests for terminal-UI slash commands.

This module enforces the parity invariant that every slash command handler
registered in ``CommandProcessor.commands`` resolves to a real method on
``AgentClient`` when it claims to reach the backend, and that every method on
``AgentClient`` references a known backend endpoint in its source.

The tests use pure source introspection (``inspect.getsource`` + regex) and
never open a socket, so the entire module runs in well under five seconds.
They are marked ``integration`` so CI runs them by default while allowing
``pytest -m "not integration"`` to skip them when iterating on unit tests.

Failure modes:

* A slash command gets added that calls ``self.app._client.foo()`` where
  ``foo`` is not defined on ``AgentClient`` -- the test prints the offending
  method and command name.
* A new ``AgentClient`` method is added without any HTTP verb or path in its
  body -- the test prints the method name.

Both failures flag a parity bug that a human must resolve: either the new
client method needs to be written, or the command handler needs to stop
calling a non-existent method.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from typing import Any

import pytest

from agent_terminal_ui.client import AgentClient
from agent_terminal_ui.commands import CommandProcessor

pytestmark = pytest.mark.integration


_CLIENT_CALL_PATTERN = re.compile(r"self\.app\.(?:_client|agent_client)\.(\w+)")

_HTTP_VERB_PATTERN = re.compile(r"\b(GET|POST|PUT|DELETE|PATCH)\b")

_PATH_IN_SOURCE_PATTERN = re.compile(
    r"""["'`][^"'`]*?"""
    r"""(?:/api/|/mcp/|/acp|/a2a|/chats|/health|/stream|/ag-ui"""
    r"""|/sessions|/rpc/|/api/approve)[^"'`]*["'`]"""
)

_SELF_DELEGATION_PATTERN = re.compile(r"self\.(\w+)\s*\(")


def _iter_command_handlers(
    processor: CommandProcessor,
) -> list[tuple[str, Callable[..., Any]]]:
    """Return a deduplicated list of (command_name, handler) pairs.

    Aliases that point at an already-seen handler are collapsed so each
    bound method is only introspected once.
    """
    seen: set[int] = set()
    result: list[tuple[str, Callable[..., Any]]] = []
    for name, handler in processor.commands.items():
        handler_id = id(handler)
        if handler_id in seen:
            continue
        seen.add(handler_id)
        result.append((name, handler))
    return result


def _extract_client_methods(handler: Callable[..., Any]) -> set[str]:
    """Return every method name called on ``self.app._client`` or ``.agent_client``.

    Uses source inspection so we catch static references even if the call
    path is gated by runtime branches.
    """
    try:
        source = inspect.getsource(handler)
    except (OSError, TypeError):
        return set()
    return set(_CLIENT_CALL_PATTERN.findall(source))


def _public_async_methods(cls: type) -> list[str]:
    """Return public async method names declared on ``cls``.

    Includes both plain coroutines and async generators (e.g. ``stream``,
    ``stream_events``) since both dispatch real HTTP traffic. Private
    helpers and cleanup coroutines (``close``, ``aclose``) are filtered
    because they are not required to reference a backend endpoint.
    """
    skip = {"close", "aclose"}
    names: list[str] = []
    for name, value in inspect.getmembers(cls, predicate=callable):
        if name.startswith("_") or name in skip:
            continue
        if inspect.iscoroutinefunction(value) or inspect.isasyncgenfunction(value):
            names.append(name)
    return names


@pytest.fixture
def processor() -> CommandProcessor:
    """Instantiate a ``CommandProcessor`` with a stand-in app object.

    The commands registry is populated in ``__init__`` regardless of the
    runtime state of ``self.app``, so a bare ``object()`` suffices.
    """
    return CommandProcessor(app=object())


class TestCommandMethodsMapToClient:
    """Each slash command's client calls must resolve to a real AgentClient method."""

    def test_every_called_method_exists_on_client(
        self, processor: CommandProcessor
    ) -> None:
        """Slash commands must only call methods defined on ``AgentClient``."""
        client_methods = {
            name for name in dir(AgentClient) if not name.startswith("__")
        }
        missing: list[tuple[str, str]] = []

        for command_name, handler in _iter_command_handlers(processor):
            for method_name in _extract_client_methods(handler):
                if method_name not in client_methods:
                    missing.append((command_name, method_name))

        if missing:
            rendered = "\n".join(
                f"  - /{cmd} calls AgentClient.{method} (not defined)"
                for cmd, method in missing
            )
            pytest.fail(
                "Slash commands reference AgentClient methods that do not "
                f"exist:\n{rendered}"
            )

    def test_extracted_methods_are_non_empty_for_http_commands(
        self, processor: CommandProcessor
    ) -> None:
        """At least one command handler must call a known HTTP client method.

        Guards against a future refactor silently stripping all backend
        references (e.g. replacing ``self.app._client.foo`` with a helper
        indirection the regex cannot see).
        """
        seen_methods: set[str] = set()
        for _, handler in _iter_command_handlers(processor):
            seen_methods.update(_extract_client_methods(handler))

        assert seen_methods, (
            "No client methods were extracted from any command handler. "
            "Either the regex is broken or all backend calls have been "
            "routed through an indirection."
        )


class TestClientMethodsReferenceBackendRoutes:
    """Each AgentClient method must reference a documented backend route."""

    def test_every_public_async_method_has_http_path_in_source(self) -> None:
        """Every public async method must reference a backend route.

        A method passes the soft check if any of the following holds:

        * Its source contains a well-known endpoint prefix
          (``/api/``, ``/mcp/``, ``/acp``, ``/a2a``, ``/chats``,
          ``/health``, ``/stream``, ``/ag-ui``, ``/sessions``, ``/rpc/``,
          ``/api/approve``) in a string literal or f-string.
        * Its docstring documents an HTTP verb alongside a path-like token.
        * It is a thin alias that delegates to another public method on
          ``self`` (e.g. ``get_impact`` -> ``get_graph_impact``).
        """
        public = set(_public_async_methods(AgentClient))
        violators: list[str] = []
        for name in public:
            method = getattr(AgentClient, name)
            try:
                source = inspect.getsource(method)
            except (OSError, TypeError):
                continue

            has_path = bool(_PATH_IN_SOURCE_PATTERN.search(source))
            doc = inspect.getdoc(method) or ""
            has_documented_verb = bool(
                _HTTP_VERB_PATTERN.search(doc) and re.search(r"[/`'\"]/?\w+", doc)
            )
            delegates = {
                match
                for match in _SELF_DELEGATION_PATTERN.findall(source)
                if match in public and match != name
            }

            if not has_path and not has_documented_verb and not delegates:
                violators.append(name)

        if violators:
            rendered = "\n".join(f"  - AgentClient.{n}" for n in violators)
            pytest.fail(
                "Public AgentClient methods must reference a backend route "
                "(URL literal, documented HTTP verb + path, or delegate "
                f"to another client method):\n{rendered}"
            )

    def test_client_methods_declare_coroutines(self) -> None:
        """Non-cleanup public client methods must be async.

        A synchronous HTTP call would break streaming and violate the
        project's protocol-first design principles. Both plain coroutines
        (``await resp = self._http_client.get(...)``) and async generators
        (``async def stream(...)``) are accepted.
        """
        offenders: list[str] = []
        for name, value in inspect.getmembers(AgentClient):
            if name.startswith("_") or name == "close":
                continue
            if not (inspect.isfunction(value) or inspect.ismethod(value)):
                continue
            if not (
                inspect.iscoroutinefunction(value) or inspect.isasyncgenfunction(value)
            ):
                offenders.append(name)
        if offenders:
            rendered = ", ".join(offenders)
            pytest.fail(f"AgentClient methods must be async: {rendered}")


class TestCommandRegistry:
    """Smoke checks on the command registry itself."""

    def test_registry_is_non_empty(self, processor: CommandProcessor) -> None:
        """The commands registry must have at least the core command set."""
        assert len(processor.commands) >= 10

    def test_every_handler_is_callable(self, processor: CommandProcessor) -> None:
        """Every registered handler must be a coroutine function."""
        for name, handler in processor.commands.items():
            assert inspect.iscoroutinefunction(handler), (
                f"Command /{name} must be an async coroutine"
            )

    def test_aliases_share_target_handler(self, processor: CommandProcessor) -> None:
        """Declared aliases must resolve to their canonical handler.

        Bound-method identity (``is``) is unstable across repeated lookups
        because ``CPython`` synthesises a fresh ``MethodType`` on each
        attribute access, so we compare the underlying function via
        ``__func__`` instead.
        """
        for alias, canonical in processor.canonical_commands.items():
            alias_func = getattr(
                processor.commands[alias], "__func__", processor.commands[alias]
            )
            canon_func = getattr(
                processor.commands[canonical],
                "__func__",
                processor.commands[canonical],
            )
            assert alias_func is canon_func, (
                f"Alias /{alias} does not share the handler of /{canonical}"
            )
