"""Schema-driven capability browser, preflight, and invocation screens."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, ClassVar

from rich.markup import escape
from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, ListItem, ListView, Select, Static

from agent_terminal_ui.capabilities import (
    CapabilityAction,
    CapabilityCatalog,
    CapabilityDescriptor,
    CapabilityInvocation,
    CapabilityPreflight,
    SchemaField,
    SchemaInputError,
    parse_schema_input,
    schema_default_text,
    schema_fields,
)
from agent_terminal_ui.client import AgentClient


class CapabilityConfirmationScreen(ModalScreen[bool]):
    """Explicit confirmation boundary for mutating or policy-gated actions."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("y", "confirm", "Confirm", show=False),
        Binding("n", "cancel", "Cancel", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    CapabilityConfirmationScreen {
        align: center middle;
    }

    #capability-confirm-dialog {
        width: 80%;
        max-width: 90;
        height: 75%;
        background: $surface;
        border: thick $warning;
        padding: 1 2;
    }

    #capability-confirm-title {
        height: 2;
        text-style: bold;
        color: $warning;
        text-align: center;
    }

    #capability-confirm-body {
        height: 1fr;
    }

    #capability-confirm-actions {
        height: 3;
        align-horizontal: right;
    }
    """

    def __init__(
        self,
        descriptor: CapabilityDescriptor,
        action: CapabilityAction,
        inputs: dict[str, Any],
        preflight: CapabilityPreflight,
    ) -> None:
        super().__init__()
        self.descriptor = descriptor
        self.capability_action = action
        self.inputs = inputs
        self.preflight = preflight

    def compose(self) -> ComposeResult:
        policy = self.preflight.policy
        policy_lines = [
            f"Capability: {self.descriptor.title} ({self.descriptor.id})",
            f"Action: {self.capability_action.id}",
            f"Mutates: {self.preflight.side_effects.mutates}",
            f"Policy preview: {policy.get('decision', 'unknown')}",
            f"Approval required: {bool(policy.get('approval_required'))}",
            "The gateway will recheck policy and identity at execution.",
        ]
        reason = policy.get("reason")
        if reason:
            policy_lines.append(f"Reason: {reason}")

        with Vertical(id="capability-confirm-dialog"):
            yield Static(
                "Confirm Capability Side Effect", id="capability-confirm-title"
            )
            with VerticalScroll(id="capability-confirm-body"):
                yield Static("\n".join(escape(line) for line in policy_lines))
                yield Static(
                    Syntax(
                        json.dumps(self.inputs, indent=2, sort_keys=True, default=str),
                        "json",
                        word_wrap=True,
                    )
                )
            with Horizontal(id="capability-confirm-actions"):
                yield Button("Cancel", id="capability-confirm-cancel")
                yield Button(
                    "Confirm and invoke",
                    id="capability-confirm-accept",
                    variant="warning",
                )

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "capability-confirm-accept":
            self.action_confirm()
        elif event.button.id == "capability-confirm-cancel":
            self.action_cancel()


@dataclass(frozen=True, slots=True)
class _PendingCapabilityApproval:
    """The exact broker request and server-bound identities awaiting approval."""

    descriptor: CapabilityDescriptor
    action: CapabilityAction
    inputs: dict[str, Any]
    target: str | None
    invocation: CapabilityInvocation


class CapabilityPaletteScreen(ModalScreen[None]):
    """Search capabilities, generate inputs from schemas, and invoke safely."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    CapabilityPaletteScreen {
        align: center middle;
    }

    #capability-palette-dialog {
        width: 96%;
        height: 92%;
        background: $surface;
        border: thick $primary;
        padding: 1;
    }

    #capability-palette-title {
        height: 2;
        text-align: center;
        text-style: bold;
        color: $primary;
    }

    #capability-palette-status {
        height: auto;
        min-height: 2;
        color: $text-muted;
        padding: 0 1;
    }

    #capability-palette-search {
        height: 3;
    }

    #capability-palette-body {
        height: 1fr;
    }

    #capability-palette-list-pane {
        width: 34%;
        min-width: 28;
        border-right: solid $primary 30%;
        padding-right: 1;
    }

    #capability-palette-list {
        height: 1fr;
    }

    #capability-palette-list ListItem {
        height: auto;
        min-height: 2;
        padding: 0 1;
    }

    #capability-palette-detail {
        width: 1fr;
        height: 1fr;
        padding: 0 1;
    }

    #capability-description,
    #capability-action-contract,
    #capability-preflight,
    #capability-result {
        height: auto;
        min-height: 2;
        margin-bottom: 1;
    }

    #capability-action-select {
        margin-bottom: 1;
    }

    #capability-form-fields {
        height: auto;
    }

    .capability-field-label {
        height: auto;
        min-height: 1;
        color: $text-muted;
    }

    .capability-field-input {
        margin-bottom: 1;
    }

    #capability-palette-actions {
        height: 3;
        align-horizontal: right;
    }
    """

    def __init__(
        self,
        client: AgentClient,
        *,
        initial_query: str = "",
        capability_id: str | None = None,
    ) -> None:
        super().__init__()
        self.client = client
        self.initial_query = initial_query
        self.initial_capability_id = capability_id
        self.catalog: CapabilityCatalog | None = None
        self.filtered: list[CapabilityDescriptor] = []
        self.descriptor: CapabilityDescriptor | None = None
        self.capability_action: CapabilityAction | None = None
        self.form_fields: tuple[SchemaField, ...] = ()
        self.field_widget_ids: dict[str, str] = {}
        self.preflight: CapabilityPreflight | None = None
        self.run_id: str | None = None
        self._pending_approval: _PendingCapabilityApproval | None = None
        self._detail_live = False
        self._suppress_action_change = False

    def compose(self) -> ComposeResult:
        with Vertical(id="capability-palette-dialog"):
            yield Static("Live Capability Palette", id="capability-palette-title")
            yield Static("Loading catalog...", id="capability-palette-status")
            yield Input(
                value=self.initial_query,
                placeholder="Search capability IDs, actions, intents, or tags",
                id="capability-palette-search",
            )
            with Horizontal(id="capability-palette-body"):
                with Vertical(id="capability-palette-list-pane"):
                    yield ListView(id="capability-palette-list")
                with VerticalScroll(id="capability-palette-detail"):
                    yield Static(
                        "Select a capability to inspect its live schema.",
                        id="capability-description",
                    )
                    yield Select(
                        [],
                        prompt="Select an action",
                        allow_blank=True,
                        id="capability-action-select",
                        disabled=True,
                    )
                    yield Static("", id="capability-action-contract")
                    yield Vertical(id="capability-form-fields")
                    yield Static("", id="capability-preflight")
                    yield Static("", id="capability-result")
            with Horizontal(id="capability-palette-actions"):
                yield Button(
                    "Preflight", id="capability-preflight-button", disabled=True
                )
                yield Button(
                    "Invoke",
                    id="capability-invoke-button",
                    variant="primary",
                    disabled=True,
                )
                yield Button(
                    "Inspect run", id="capability-inspect-button", disabled=True
                )
                yield Button(
                    "Approve & resume",
                    id="capability-approve-button",
                    variant="warning",
                    disabled=True,
                )
                yield Button(
                    "Deny",
                    id="capability-deny-button",
                    variant="error",
                    disabled=True,
                )
                yield Button("Close", id="capability-close-button")

    def on_mount(self) -> None:
        self.run_worker(
            self._load_catalog(),
            group="capability-palette-load",
            exclusive=True,
            name="load capability palette",
        )

    def action_close(self) -> None:
        self.dismiss()

    def _set_status(self, message: str, *, color: str | None = None) -> None:
        rendered = escape(message)
        if color:
            rendered = f"[{color}]{rendered}[/{color}]"
        self.query_one("#capability-palette-status", Static).update(rendered)

    async def _load_catalog(self) -> None:
        self._set_status("Loading live capability catalog...")
        try:
            self.catalog = await self.client.list_capabilities(include_actions=True)
        except Exception as exc:
            self._set_status(
                f"Capability catalog unavailable: {type(exc).__name__}: {exc}",
                color="yellow",
            )
            self.filtered = []
            self._render_list()
            return

        self._filter(self.initial_query)
        selected = None
        if self.initial_capability_id:
            selected = self.catalog.find(self.initial_capability_id)
        if selected is None and self.filtered:
            selected = self.filtered[0]
        if selected is not None:
            await self._load_descriptor(selected.id)
            if selected in self.filtered:
                self.query_one(
                    "#capability-palette-list", ListView
                ).index = self.filtered.index(selected)
        elif not self.catalog.capabilities:
            runtime = str(self.catalog.runtime.get("status") or "unknown")
            self._set_status(
                f"The gateway returned an empty catalog (runtime: {runtime}).",
                color="yellow",
            )

    def _filter(self, query: str) -> None:
        capabilities = self.catalog.capabilities if self.catalog else ()
        normalized = query.strip().lower()
        self.filtered = [
            capability
            for capability in capabilities
            if not normalized or normalized in capability.search_text
        ]
        self._render_list()
        if self.catalog is not None:
            runtime = str(self.catalog.runtime.get("status") or "unknown")
            counts = (
                f"{len(self.filtered)} of {len(self.catalog.capabilities)} "
                "capabilities. "
            )
            self._set_status(f"{counts}Gateway runtime: {runtime}.")

    def _render_list(self) -> None:
        list_view = self.query_one("#capability-palette-list", ListView)
        list_view.clear()
        for capability in self.filtered:
            availability = capability.availability
            status = availability.status
            color = {
                "available": "green",
                "degraded": "yellow",
                "unavailable": "red",
            }.get(status, "dim")
            if availability.is_available and availability.readiness == "cold":
                color = "cyan"
            list_view.append(
                ListItem(
                    Static(
                        f"[{color}]●[/{color}] "
                        f"[bold]{escape(capability.title)}[/bold]\n"
                        f"[dim]{escape(capability.id)} · "
                        f"{len(capability.actions)} actions[/dim]"
                    )
                )
            )

    async def _load_descriptor(
        self, capability_id: str, action_id: str | None = None
    ) -> None:
        if self.descriptor is not None and self.descriptor.id == capability_id:
            if (
                action_id
                and self.capability_action
                and self.capability_action.id != action_id
            ):
                action = self.descriptor.action(action_id)
                if action is not None:
                    await self._render_action(action)
            return

        self._detail_live = False
        self.preflight = None
        self.query_one("#capability-preflight-button", Button).disabled = True
        self.query_one("#capability-invoke-button", Button).disabled = True
        self._set_status(f"Loading {capability_id} detail...")
        try:
            live_descriptor = await self.client.get_capability(capability_id)
        except Exception as exc:
            fallback = self.catalog.find(capability_id) if self.catalog else None
            if fallback is None:
                self._set_status(
                    f"Capability detail unavailable: {type(exc).__name__}: {exc}",
                    color="yellow",
                )
                return
            descriptor = fallback
            self._set_status(
                "Capability detail endpoint is unavailable. Showing the catalog "
                "snapshot read-only; preflight and invocation are disabled.",
                color="yellow",
            )
        else:
            descriptor = live_descriptor
            self._detail_live = True

        self.descriptor = descriptor
        await self._render_descriptor(descriptor, action_id=action_id)

    async def _render_descriptor(
        self, descriptor: CapabilityDescriptor, *, action_id: str | None = None
    ) -> None:
        availability = descriptor.availability
        missing = ", ".join(availability.missing_preconditions)
        renderer = str(descriptor.render.get("renderer") or "json")
        lines = [
            f"[bold]{escape(descriptor.title)}[/bold] "
            f"[dim]{escape(descriptor.id)}[/dim]",
            escape(descriptor.one_line or "No description provided."),
            f"Availability: [{self._availability_color(availability.status)}]"
            f"{escape(availability.display_status)}[/]",
            f"Renderer hint: {escape(renderer)}",
        ]
        if missing:
            lines.append(f"Missing: {escape(missing)}")
        if availability.is_available and availability.readiness == "cold":
            lines.append(
                "[cyan]Callable now; the first invocation will warm the backend.[/cyan]"
            )
        self.query_one("#capability-description", Static).update("\n".join(lines))

        action_select = self.query_one("#capability-action-select", Select)
        actions = descriptor.actions
        action_select.set_options(
            [(action.id.replace("_", " "), action.id) for action in actions]
        )
        action_select.disabled = not actions
        selected = descriptor.action(action_id)
        if selected is None and actions:
            selected = actions[0]

        self._suppress_action_change = True
        if selected is not None:
            action_select.value = selected.id
        self._suppress_action_change = False

        if selected is not None:
            await self._render_action(selected)
        else:
            self.capability_action = None
            await self.query_one("#capability-form-fields", Vertical).remove_children()
            self._set_status(
                f"{descriptor.id} declares no invocable actions.", color="yellow"
            )

    @staticmethod
    def _availability_color(status: str) -> str:
        return {
            "available": "green",
            "degraded": "yellow",
            "unavailable": "red",
        }.get(status, "dim")

    async def _render_action(self, action: CapabilityAction) -> None:
        self.capability_action = action
        self.form_fields = schema_fields(action.input_schema)
        self.field_widget_ids = {}
        self.preflight = None
        self.query_one("#capability-preflight", Static).update("")
        self.query_one("#capability-result", Static).update("")
        route = action.rest_route or "not registered"
        encoding = action.request_encoding or "not declared"
        mutates = action.side_effects.mutates
        invoke_route = (
            self.descriptor.governed_invoke_route if self.descriptor else None
        ) or "unavailable"
        eventual_event = (
            str(self.descriptor.execution.get("eventual_result_event") or "unknown")
            if self.descriptor
            else "unknown"
        )
        self.query_one("#capability-action-contract", Static).update(
            "\n".join(
                (
                    f"[bold]Action contract[/bold]: {escape(action.id)}",
                    f"Governed invoke: {escape(invoke_route)}",
                    f"Legacy direct REST: {escape(route)} ({escape(encoding)}; "
                    f"frontend executable: {action.frontend_executable})",
                    f"Asynchronous result event: {escape(eventual_event)}",
                    f"Mutates: {mutates}",
                )
            )
        )
        container = self.query_one("#capability-form-fields", Vertical)
        await container.remove_children()

        widgets: list[Static | Input] = []
        for index, schema_field in enumerate(self.form_fields):
            widget_id = f"capability-field-{index}"
            self.field_widget_ids[schema_field.name] = widget_id
            requirement = "required" if schema_field.required else "optional"
            description = schema_field.description
            enum = schema_field.schema.get("enum")
            detail = f"{schema_field.kind}, {requirement}"
            if isinstance(enum, list):
                detail += "; choices: " + ", ".join(str(item) for item in enum)
            if description:
                detail += f". {description}"
            widgets.append(
                Static(
                    f"[bold]{escape(schema_field.name)}[/bold] "
                    f"[dim]{escape(detail)}[/dim]",
                    classes="capability-field-label",
                )
            )
            lowered = schema_field.name.lower()
            widgets.append(
                Input(
                    value=schema_default_text(schema_field),
                    placeholder=f"Enter {schema_field.kind}",
                    password=any(
                        secret in lowered
                        for secret in ("password", "secret", "token", "api_key")
                    ),
                    id=widget_id,
                    classes="capability-field-input",
                    disabled="const" in schema_field.schema,
                )
            )
        if widgets:
            await container.mount(*widgets)
        else:
            await container.mount(
                Static("[dim]This action declares no input fields.[/dim]")
            )

        enabled = self._detail_live
        invocable = self._action_invocable(action)
        self.query_one("#capability-preflight-button", Button).disabled = not enabled
        self.query_one("#capability-invoke-button", Button).disabled = not (
            enabled
            and invocable
            and self.descriptor
            and self.descriptor.availability.is_available
        )
        if enabled and not invocable:
            self._set_status(
                "This action has no stable action ID; governed invocation is "
                "unavailable.",
                color="yellow",
            )

    @staticmethod
    def _action_invocable(action: CapabilityAction | None) -> bool:
        """Whether an action can be selected for governed broker invocation."""
        return bool(action and action.id)

    def _collect_inputs(self) -> dict[str, Any]:
        inputs: dict[str, Any] = {}
        for schema_field in self.form_fields:
            widget_id = self.field_widget_ids[schema_field.name]
            raw_value = self.query_one(f"#{widget_id}", Input).value
            present, value = parse_schema_input(schema_field, raw_value)
            if present:
                inputs[schema_field.name] = value
        return inputs

    async def _preflight_current(
        self, inputs: dict[str, Any]
    ) -> CapabilityPreflight | None:
        if self.descriptor is None or self.capability_action is None:
            return None
        try:
            preflight = await self.client.preflight_capability(
                self.descriptor.id,
                action=self.capability_action.id,
                inputs=inputs,
            )
        except Exception as exc:
            self._set_status(
                f"Preflight unavailable: {type(exc).__name__}: {exc}", color="yellow"
            )
            return None
        self.preflight = preflight
        self._render_preflight(preflight)
        return preflight

    def _render_preflight(self, preflight: CapabilityPreflight) -> None:
        policy = preflight.policy
        lines = [
            "[bold]Preflight preview[/bold]",
            f"Valid: {preflight.valid} · Eligible: {preflight.eligible} · "
            f"Executable now: {preflight.executable_now}",
            f"Policy: {escape(str(policy.get('decision') or 'unknown'))} · "
            f"Approval required: {bool(policy.get('approval_required'))}",
            "[dim]Identity is not evaluated here; policy is authoritative only at "
            "execution.[/dim]",
        ]
        if preflight.validation_issues:
            lines.extend(
                f"[red]{escape(issue.field)}: {escape(issue.message)}[/red]"
                for issue in preflight.validation_issues
            )
        if not preflight.availability.is_available:
            lines.append(
                f"[yellow]Availability: {escape(preflight.availability.status)} "
                f"({escape(preflight.availability.explanation)})[/yellow]"
            )
        elif preflight.availability.readiness == "cold":
            lines.append(
                "[cyan]Callable cold start: the first invocation warms the "
                "backend.[/cyan]"
            )
        self.query_one("#capability-preflight", Static).update("\n".join(lines))
        self.query_one("#capability-invoke-button", Button).disabled = not (
            preflight.executable_now
            and self._detail_live
            and self._action_invocable(self.capability_action)
        )

    async def _show_preflight(self) -> None:
        try:
            inputs = self._collect_inputs()
        except SchemaInputError as exc:
            self._set_status(str(exc), color="red")
            return
        self._set_status("Running non-executing preflight...")
        preflight = await self._preflight_current(inputs)
        if preflight is not None:
            color = "green" if preflight.executable_now else "yellow"
            self._set_status(
                "Preflight passed; ready to invoke."
                if preflight.executable_now
                else "Preflight completed, but execution is not currently available.",
                color=color,
            )

    async def _prepare_invocation(self) -> None:
        if self.descriptor is None or self.capability_action is None:
            return
        try:
            inputs = self._collect_inputs()
        except SchemaInputError as exc:
            self._set_status(str(exc), color="red")
            return

        self._set_status("Re-running preflight immediately before invocation...")
        preflight = await self._preflight_current(inputs)
        if preflight is None or not preflight.executable_now:
            self._set_status(
                "Invocation blocked because preflight is unavailable or not "
                "executable.",
                color="yellow",
            )
            return

        if preflight.requires_confirmation:
            descriptor = self.descriptor
            action = self.capability_action

            def after_confirmation(confirmed: bool | None) -> None:
                if confirmed:
                    self.run_worker(
                        self._invoke_after_confirmation(descriptor, action, inputs),
                        group="capability-invoke",
                        exclusive=True,
                    )
                else:
                    self._set_status("Invocation cancelled by operator.")

            self.app.push_screen(
                CapabilityConfirmationScreen(descriptor, action, inputs, preflight),
                after_confirmation,
            )
            return
        await self._invoke(self.descriptor, self.capability_action, inputs)

    async def _invoke_after_confirmation(
        self,
        descriptor: CapabilityDescriptor,
        action: CapabilityAction,
        inputs: dict[str, Any],
    ) -> None:
        """Recheck the preview after operator think time, then invoke."""
        self._set_status("Confirmation accepted; rechecking preflight...")
        preflight = await self._preflight_current(inputs)
        if preflight is None or not preflight.executable_now:
            self._set_status(
                "Invocation blocked because the post-confirmation preflight is not "
                "executable.",
                color="yellow",
            )
            return
        await self._invoke(descriptor, action, inputs)

    async def _invoke(
        self,
        descriptor: CapabilityDescriptor,
        action: CapabilityAction,
        inputs: dict[str, Any],
        *,
        target: str | None = None,
        approval_id: str | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        if session_id is None:
            try:
                session_id = await self._stable_session_id()
            except Exception as exc:
                self._set_status(
                    "Invocation blocked because a stable session could not be "
                    f"created: {type(exc).__name__}: {exc}",
                    color="yellow",
                )
                return
        if not session_id:
            self._set_status(
                "Invocation blocked because no stable session identity is available.",
                color="yellow",
            )
            return

        self._set_status(
            "Invoking through the gateway's governed capability boundary..."
        )
        try:
            invocation = await self.client.invoke_capability(
                descriptor.id,
                inputs,
                action=action.id,
                target=target,
                approval_id=approval_id,
                run_id=run_id,
                session_id=session_id,
            )
        except Exception as exc:
            self._set_status(
                f"Invocation failed: {type(exc).__name__}: {exc}", color="red"
            )
            return

        result = invocation.result
        rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
        self.query_one("#capability-result", Static).update(
            Syntax(rendered, "json", word_wrap=True)
        )

        self._remember_invocation_identity(invocation)
        if invocation.approval_required:
            if not (
                invocation.approval_id and invocation.run_id and invocation.session_id
            ):
                self._set_status(
                    "The gateway requested approval without complete server-bound "
                    "approval, run, and session identities; automatic resume is "
                    "disabled.",
                    color="red",
                )
                return
            self._pending_approval = _PendingCapabilityApproval(
                descriptor=descriptor,
                action=action,
                inputs=copy.deepcopy(inputs),
                target=target,
                invocation=invocation,
            )
            self._set_approval_buttons(enabled=True)
            self.query_one("#capability-preflight-button", Button).disabled = True
            self.query_one("#capability-invoke-button", Button).disabled = True
            self._set_status(
                f"Run {invocation.run_id} is waiting for approval "
                f"{invocation.approval_id}. Approve to resume this exact request, "
                "or deny it.",
                color="yellow",
            )
            return

        if invocation.accepted:
            self._pending_approval = None
            self._set_approval_buttons(enabled=False)
            if self.run_id:
                self._set_status(
                    f"Invocation accepted. Run {self.run_id} is executing; inspect "
                    "its events for the eventual tool_result.",
                    color="cyan",
                )
            else:
                self._set_status(
                    "The gateway accepted execution without a run_id; lifecycle "
                    "tracking is unavailable.",
                    color="yellow",
                )
            return

        if not invocation.succeeded:
            self._set_status("The gateway returned an error result.", color="red")
            return

        self._pending_approval = None
        self._set_approval_buttons(enabled=False)
        if self.run_id:
            self._set_status(
                f"Invocation completed. Run {self.run_id} is available for replay.",
                color="green",
            )
        else:
            self._set_status(
                "Invocation completed without a run_id. Event replay is unavailable "
                "for this result.",
                color="green",
            )

    async def _stable_session_id(self) -> str | None:
        """Return or create the stable session used by governed executions."""
        session_id = getattr(self.app, "current_session_id", None) or getattr(
            self.client, "current_session_id", None
        )
        if session_id:
            return str(session_id)
        create_session = getattr(self.client, "create_session", None)
        if not callable(create_session):
            return None
        created = await create_session()
        if created:
            remember_session = getattr(self.app, "remember_session_id", None)
            if callable(remember_session):
                remember_session(str(created))
            return str(created)
        return None

    def _remember_invocation_identity(self, invocation: CapabilityInvocation) -> None:
        """Preserve independent server-bound session and run identities."""
        if invocation.session_id:
            remember_session = getattr(self.app, "remember_session_id", None)
            if callable(remember_session):
                remember_session(invocation.session_id)
        self.run_id = invocation.run_id
        self.query_one("#capability-inspect-button", Button).disabled = (
            self.run_id is None
        )
        if self.run_id:
            remember_run = getattr(self.app, "remember_run_id", None)
            if callable(remember_run):
                remember_run(self.run_id)

    def _set_approval_buttons(self, *, enabled: bool) -> None:
        self.query_one("#capability-approve-button", Button).disabled = not enabled
        self.query_one("#capability-deny-button", Button).disabled = not enabled

    async def _resolve_pending_approval(self, decision: str) -> None:
        """Grant/deny a pending approval and resume only the exact bound request."""
        pending = self._pending_approval
        if pending is None:
            self._set_status("There is no pending capability approval.", color="yellow")
            return
        approval_id = pending.invocation.approval_id
        run_id = pending.invocation.run_id
        session_id = pending.invocation.session_id
        if not approval_id or not run_id or not session_id:
            self._set_status(
                "Pending approval identity is incomplete; resume is disabled.",
                color="red",
            )
            return

        self._set_approval_buttons(enabled=False)
        self._set_status(f"Recording {decision} for approval {approval_id}...")
        try:
            response = await self.client.grant_fleet_approval(approval_id, decision)
        except Exception as exc:
            self._set_approval_buttons(enabled=True)
            self._set_status(
                f"Approval update failed: {type(exc).__name__}: {exc}", color="red"
            )
            return

        self.query_one("#capability-result", Static).update(
            Syntax(
                json.dumps(response, indent=2, sort_keys=True, default=str),
                "json",
                word_wrap=True,
            )
        )
        if decision == "denied":
            self._pending_approval = None
            self._set_status(
                f"Approval {approval_id} was denied; run {run_id} was not resumed.",
                color="yellow",
            )
            return

        self._set_status(
            f"Approval {approval_id} granted; resuming the exact bound request..."
        )
        await self._invoke(
            pending.descriptor,
            pending.action,
            pending.inputs,
            target=pending.target,
            approval_id=approval_id,
            run_id=run_id,
            session_id=session_id,
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "capability-palette-search":
            self._filter(event.value)
        elif event.input.id and event.input.id.startswith("capability-field-"):
            self.preflight = None
            self.query_one("#capability-preflight", Static).update(
                "[dim]Inputs changed; preflight will run again before invocation.[/dim]"
            )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "capability-palette-list":
            return
        index = event.list_view.index
        if index is None or index >= len(self.filtered):
            return
        self.run_worker(
            self._load_descriptor(self.filtered[index].id),
            group="capability-detail",
            exclusive=True,
        )

    async def on_select_changed(self, event: Select.Changed) -> None:
        if (
            event.select.id != "capability-action-select"
            or self._suppress_action_change
        ):
            return
        if self.descriptor is None or event.value is Select.NULL:
            return
        action = self.descriptor.action(str(event.value))
        if action is not None and action != self.capability_action:
            await self._render_action(action)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "capability-close-button":
            self.action_close()
        elif button_id == "capability-preflight-button":
            self.run_worker(
                self._show_preflight(), group="capability-preflight", exclusive=True
            )
        elif button_id == "capability-invoke-button":
            self.run_worker(
                self._prepare_invocation(),
                group="capability-preflight",
                exclusive=True,
            )
        elif button_id == "capability-inspect-button" and self.run_id:
            from agent_terminal_ui.tui.run_inspector import RunInspectorScreen

            self.app.push_screen(RunInspectorScreen(self.client, self.run_id))
        elif button_id == "capability-approve-button":
            self.run_worker(
                self._resolve_pending_approval("approved"),
                group="capability-approval",
                exclusive=True,
            )
        elif button_id == "capability-deny-button":
            self.run_worker(
                self._resolve_pending_approval("denied"),
                group="capability-approval",
                exclusive=True,
            )
