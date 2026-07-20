"""Typed frontend models for the gateway capability and run contracts.

The terminal UI deliberately owns these lightweight models instead of importing
``agent_utilities`` in-process. The gateway remains the source of truth while
the frontend gets a stable, testable boundary for schema-driven rendering.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, TypeGuard


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


TerminalRunEventType = Literal[
    "run_completed",
    "run_failed",
    "run_interrupted",
    "run_cancelled",
    "error",
]

TERMINAL_RUN_EVENT_TYPES: frozenset[TerminalRunEventType] = frozenset(
    {
        "run_completed",
        "run_failed",
        "run_interrupted",
        "run_cancelled",
        "error",
    }
)


def is_terminal_run_event_type(
    event_type: str,
) -> TypeGuard[TerminalRunEventType]:
    """Return whether an event ends canonical run follow.

    Graph lifecycle events such as ``graph_complete`` are progress. A graph can
    finish before ``final_output`` and the authoritative ``run_completed`` event
    arrive, so frontends must not infer terminality from graph-level names.
    """
    return event_type in TERMINAL_RUN_EVENT_TYPES


@dataclass(frozen=True, slots=True)
class CapabilityAvailability:
    """Runtime availability reported by the gateway catalog."""

    status: str = "unknown"
    readiness: str | None = None
    reasons: tuple[str, ...] = ()
    missing_preconditions: tuple[str, ...] = ()

    @classmethod
    def from_payload(cls, payload: Any) -> CapabilityAvailability:
        data = _mapping(payload)
        return cls(
            status=str(data.get("status") or "unknown"),
            readiness=(
                str(data["readiness"]) if data.get("readiness") is not None else None
            ),
            reasons=_strings(data.get("reasons")),
            missing_preconditions=_strings(data.get("missing_preconditions")),
        )

    @property
    def is_available(self) -> bool:
        """Whether the gateway says this capability can execute now."""
        return self.status == "available"

    @property
    def explanation(self) -> str:
        """A concise user-facing reason for non-available states."""
        if self.is_available and self.readiness == "cold":
            return "cold start; the first invocation warms the backend"
        details = self.reasons or self.missing_preconditions
        return ", ".join(details) if details else self.status

    @property
    def display_status(self) -> str:
        """Availability label that preserves callable cold-start semantics."""
        if self.is_available and self.readiness == "cold":
            return "available (cold)"
        return self.status


@dataclass(frozen=True, slots=True)
class CapabilitySideEffects:
    """Side-effect metadata for one capability action."""

    mutates: bool | None = None
    durability: str | None = None
    idempotent: bool | None = None
    audited: bool | None = None
    emits_cdc: bool | None = None
    transaction_participation: str | None = None

    @classmethod
    def from_payload(cls, payload: Any) -> CapabilitySideEffects:
        data = _mapping(payload)
        return cls(
            mutates=data.get("mutates")
            if isinstance(data.get("mutates"), bool)
            else None,
            durability=(
                str(data["durability"]) if data.get("durability") is not None else None
            ),
            idempotent=(
                data.get("idempotent")
                if isinstance(data.get("idempotent"), bool)
                else None
            ),
            audited=data.get("audited")
            if isinstance(data.get("audited"), bool)
            else None,
            emits_cdc=(
                data.get("emits_cdc")
                if isinstance(data.get("emits_cdc"), bool)
                else None
            ),
            transaction_participation=(
                str(data["transaction_participation"])
                if data.get("transaction_participation") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class CapabilityAction:
    """One invocable action and its JSON input schema."""

    id: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    typed_io: dict[str, Any] = field(default_factory=dict)
    side_effects: CapabilitySideEffects = field(default_factory=CapabilitySideEffects)
    policy: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> CapabilityAction:
        data = _mapping(payload)
        return cls(
            id=str(data.get("id") or ""),
            input_schema=_mapping(data.get("input_schema")),
            output_schema=_mapping(data.get("output_schema")),
            typed_io=_mapping(data.get("typed_io")),
            side_effects=CapabilitySideEffects.from_payload(data.get("side_effects")),
            policy=_mapping(data.get("policy")),
        )

    @property
    def rest_route(self) -> str | None:
        """Return legacy direct-route metadata without making it executable."""
        route = self.typed_io.get("legacy_rest_route") or self.typed_io.get(
            "rest_route"
        )
        return route if isinstance(route, str) and route.startswith("/") else None

    @property
    def request_encoding(self) -> str | None:
        """Return the legacy direct-route encoding metadata."""
        encoding = self.typed_io.get("legacy_request_encoding") or self.typed_io.get(
            "request_encoding"
        )
        return encoding if isinstance(encoding, str) else None

    @property
    def frontend_executable(self) -> bool:
        """Whether the descriptor explicitly permits direct frontend execution."""
        return self.typed_io.get("frontend_executable") is True

    @property
    def params_field(self) -> str | None:
        """Return an optional JSON-object field to expand into the REST body."""
        name = self.typed_io.get("params_field")
        return name if isinstance(name, str) and name else None


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    """A live capability descriptor reconciled by the gateway."""

    id: str
    title: str
    one_line: str
    actions: tuple[CapabilityAction, ...] = ()
    availability: CapabilityAvailability = field(default_factory=CapabilityAvailability)
    typed_io: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)
    render: dict[str, Any] = field(default_factory=dict)
    intent_verbs: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: Any) -> CapabilityDescriptor:
        data = _mapping(payload)
        capability_id = str(data.get("id") or "")
        return cls(
            id=capability_id,
            title=str(data.get("title") or capability_id.replace("_", " ")),
            one_line=str(data.get("one_line") or ""),
            actions=tuple(
                CapabilityAction.from_payload(action)
                for action in data.get("actions", [])
                if isinstance(action, dict)
            ),
            availability=CapabilityAvailability.from_payload(data.get("availability")),
            typed_io=_mapping(data.get("typed_io")),
            execution=_mapping(data.get("execution")),
            render=_mapping(data.get("render")),
            intent_verbs=_strings(data.get("intent_verbs")),
            raw=data,
        )

    @property
    def rest_route(self) -> str | None:
        """The aggregate legacy direct-route metadata, when present."""
        route = self.typed_io.get("legacy_rest_route") or self.typed_io.get(
            "rest_route"
        )
        return route if isinstance(route, str) and route.startswith("/") else None

    @property
    def governed_invoke_route(self) -> str | None:
        """Return the descriptor's normative frontend invocation boundary."""
        route = self.execution.get("governed_invoke_route")
        return route if isinstance(route, str) and route.startswith("/api/") else None

    @property
    def search_text(self) -> str:
        """Normalized text used by sidebar and command-palette search."""
        tags = self.typed_io.get("tags")
        tag_values = _strings(tags)
        return " ".join(
            (
                self.id,
                self.title,
                self.one_line,
                *self.intent_verbs,
                *tag_values,
                *(action.id for action in self.actions),
            )
        ).lower()

    def action(self, action_id: str | None = None) -> CapabilityAction | None:
        """Resolve an action, defaulting only when the choice is unambiguous."""
        if action_id:
            return next(
                (action for action in self.actions if action.id == action_id), None
            )
        return self.actions[0] if len(self.actions) == 1 else None


@dataclass(frozen=True, slots=True)
class CapabilityCatalog:
    """The versioned live capability catalog."""

    schema_version: str
    catalog_version: str
    runtime: dict[str, Any]
    capabilities: tuple[CapabilityDescriptor, ...]
    generated_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: Any) -> CapabilityCatalog:
        data = _mapping(payload)
        return cls(
            schema_version=str(data.get("schema_version") or "unknown"),
            catalog_version=str(data.get("catalog_version") or ""),
            runtime=_mapping(data.get("runtime")),
            capabilities=tuple(
                CapabilityDescriptor.from_payload(capability)
                for capability in data.get("capabilities", [])
                if isinstance(capability, dict)
            ),
            generated_at=(
                str(data["generated_at"])
                if data.get("generated_at") is not None
                else None
            ),
            raw=data,
        )

    def find(self, capability_id: str) -> CapabilityDescriptor | None:
        """Find one descriptor by stable ID."""
        return next(
            (
                capability
                for capability in self.capabilities
                if capability.id == capability_id
            ),
            None,
        )


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One field-level preflight validation issue."""

    field: str
    message: str


@dataclass(frozen=True, slots=True)
class CapabilityPreflight:
    """A non-executing validation, availability, and policy preview."""

    capability_id: str
    action: str
    valid: bool
    validation_issues: tuple[ValidationIssue, ...]
    availability: CapabilityAvailability
    policy: dict[str, Any]
    eligible: bool
    executable_now: bool
    side_effects: CapabilitySideEffects
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: Any) -> CapabilityPreflight:
        data = _mapping(payload)
        issues = tuple(
            ValidationIssue(
                field=str(issue.get("field") or ""),
                message=str(issue.get("message") or "invalid input"),
            )
            for issue in data.get("validation_issues", [])
            if isinstance(issue, dict)
        )
        return cls(
            capability_id=str(data.get("capability_id") or ""),
            action=str(data.get("action") or ""),
            valid=bool(data.get("valid")),
            validation_issues=issues,
            availability=CapabilityAvailability.from_payload(data.get("availability")),
            policy=_mapping(data.get("policy")),
            eligible=bool(data.get("eligible")),
            executable_now=bool(data.get("executable_now")),
            side_effects=CapabilitySideEffects.from_payload(data.get("side_effects")),
            raw=data,
        )

    @property
    def requires_confirmation(self) -> bool:
        """Whether the preview identifies a side effect or approval boundary."""
        return self.side_effects.mutates is not False or bool(
            self.policy.get("approval_required")
        )


@dataclass(frozen=True, slots=True)
class CapabilityInvocation:
    """A governed invocation result, including resumable approval identity."""

    capability_id: str
    result: Any
    run_id: str | None = None
    session_id: str | None = None
    approval_id: str | None = None
    status: str = "unknown"
    http_status: int | None = None
    policy: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        capability_id: str,
        payload: Any,
        *,
        http_status: int | None = None,
        requested_session_id: str | None = None,
    ) -> CapabilityInvocation:
        """Parse success or HTTP 202 approval-required broker responses."""
        data = _mapping(payload)
        return cls(
            capability_id=capability_id,
            result=payload,
            run_id=explicit_run_id(payload),
            session_id=(
                str(data["session_id"])
                if data.get("session_id") is not None
                else requested_session_id
            ),
            approval_id=(
                str(data["approval_id"])
                if data.get("approval_id") is not None
                else None
            ),
            status=str(data.get("status") or "unknown"),
            http_status=http_status,
            policy=_mapping(data.get("policy")),
        )

    @property
    def approval_required(self) -> bool:
        """Whether execution is paused on a server-bound approval."""
        return self.status == "approval_required"

    @property
    def accepted(self) -> bool:
        """Whether the broker acknowledged asynchronous execution."""
        return self.status in {"accepted", "queued", "running"}

    @property
    def succeeded(self) -> bool:
        """Whether a conventional gateway result envelope reports success."""
        return not self.approval_required and self.status not in {
            "denied",
            "error",
            "invalid",
            "unavailable",
        }


@dataclass(frozen=True, slots=True)
class RunSummary:
    """Summary for one replayable run."""

    run_id: str
    session_id: str | None
    trace_id: str | None
    status: str
    first_sequence: int
    last_sequence: int
    event_count: int
    truncated: bool
    first_timestamp: str | None
    last_timestamp: str | None
    last_event_type: str | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: Any) -> RunSummary:
        data = _mapping(payload)
        return cls(
            run_id=str(data.get("run_id") or ""),
            session_id=(
                str(data["session_id"]) if data.get("session_id") is not None else None
            ),
            trace_id=(
                str(data["trace_id"]) if data.get("trace_id") is not None else None
            ),
            status=str(data.get("status") or "unknown"),
            first_sequence=int(data.get("first_sequence") or 0),
            last_sequence=int(data.get("last_sequence") or 0),
            event_count=int(data.get("event_count") or 0),
            truncated=bool(data.get("truncated")),
            first_timestamp=(
                str(data["first_timestamp"])
                if data.get("first_timestamp") is not None
                else None
            ),
            last_timestamp=(
                str(data["last_timestamp"])
                if data.get("last_timestamp") is not None
                else None
            ),
            last_event_type=(
                str(data["last_event_type"])
                if data.get("last_event_type") is not None
                else None
            ),
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class RunCatalog:
    """Newest-first lifecycle summaries for run discovery surfaces."""

    schema_version: str
    count: int
    runs: tuple[RunSummary, ...]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: Any) -> RunCatalog:
        data = _mapping(payload)
        runs = tuple(
            RunSummary.from_payload(run)
            for run in data.get("runs", [])
            if isinstance(run, dict)
        )
        return cls(
            schema_version=str(data.get("schema_version") or "unknown"),
            count=int(data.get("count") or len(runs)),
            runs=runs,
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class RunEvent:
    """Canonical versioned event replayed by the gateway."""

    schema_version: str
    event_id: str
    sequence: int
    timestamp: str
    type: str
    run_id: str
    session_id: str | None
    trace_id: str | None
    correlation_id: str | None
    parent_event_id: str | None
    source: str
    payload: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: Any) -> RunEvent:
        data = _mapping(payload)
        return cls(
            schema_version=str(data.get("schema_version") or "unknown"),
            event_id=str(data.get("event_id") or ""),
            sequence=int(data.get("sequence") or 0),
            timestamp=str(data.get("timestamp") or ""),
            type=str(data.get("type") or "unknown"),
            run_id=str(data.get("run_id") or ""),
            session_id=(
                str(data["session_id"]) if data.get("session_id") is not None else None
            ),
            trace_id=(
                str(data["trace_id"]) if data.get("trace_id") is not None else None
            ),
            correlation_id=(
                str(data["correlation_id"])
                if data.get("correlation_id") is not None
                else None
            ),
            parent_event_id=(
                str(data["parent_event_id"])
                if data.get("parent_event_id") is not None
                else None
            ),
            source=str(data.get("source") or "agent-utilities"),
            payload=_mapping(data.get("payload")),
            raw=data,
        )

    @property
    def is_terminal(self) -> bool:
        """Whether this exact event ends live follow for its run."""
        return is_terminal_run_event_type(self.type)


@dataclass(frozen=True, slots=True)
class RunReplayGap:
    """A sequence range that fell outside the bounded replay window."""

    requested_after: int
    first_available: int

    @property
    def missing_from(self) -> int:
        return self.requested_after + 1

    @property
    def missing_through(self) -> int:
        return self.first_available - 1

    @property
    def message(self) -> str:
        missing = (
            str(self.missing_from)
            if self.missing_from == self.missing_through
            else f"{self.missing_from}-{self.missing_through}"
        )
        return (
            f"Replay reset: sequences {missing} are no longer retained; "
            f"resumed at {self.first_available}."
        )


@dataclass(frozen=True, slots=True)
class RunEventPage:
    """Cursor page from the process-local run-event replay buffer."""

    schema_version: str
    run_id: str
    after: int
    events: tuple[RunEvent, ...]
    next_after: int
    has_more: bool = False
    retained_from: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: Any) -> RunEventPage:
        data = _mapping(payload)
        after = int(data.get("after") or 0)
        events = tuple(
            RunEvent.from_payload(event)
            for event in data.get("events", [])
            if isinstance(event, dict)
        )
        return cls(
            schema_version=str(data.get("schema_version") or "unknown"),
            run_id=str(data.get("run_id") or ""),
            after=after,
            events=events,
            next_after=int(data.get("next_after") or after),
            has_more=bool(data.get("has_more")),
            retained_from=(
                int(data["retained_from"])
                if data.get("retained_from") is not None
                else None
            ),
            raw=data,
        )

    @property
    def replay_gap(self) -> RunReplayGap | None:
        """Return the gap implied by this page's retained sequence window."""
        expected = self.after + 1
        candidates: list[int] = []
        if self.retained_from is not None and self.retained_from > expected:
            candidates.append(self.retained_from)
        new_sequences = [
            event.sequence for event in self.events if event.sequence > self.after
        ]
        if new_sequences:
            first_event = min(new_sequences)
            if first_event > expected:
                candidates.append(first_event)
        if not candidates:
            return None
        return RunReplayGap(
            requested_after=self.after,
            first_available=min(candidates),
        )


@dataclass(frozen=True, slots=True)
class SchemaField:
    """One top-level JSON Schema property rendered by the capability form."""

    name: str
    schema: dict[str, Any]
    required: bool

    @property
    def kind(self) -> str:
        """Best scalar type hint for parsing user input."""
        value = self.schema.get("type")
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return next((str(item) for item in value if item != "null"), "string")
        for key in ("anyOf", "oneOf"):
            choices = self.schema.get(key)
            if isinstance(choices, list):
                for choice in choices:
                    if isinstance(choice, dict) and choice.get("type") != "null":
                        choice_type = choice.get("type")
                        if isinstance(choice_type, str):
                            return choice_type
        return "string"

    @property
    def description(self) -> str:
        return str(self.schema.get("description") or "")


class SchemaInputError(ValueError):
    """Raised when a form value cannot satisfy its advertised JSON type."""


def schema_fields(schema: dict[str, Any]) -> tuple[SchemaField, ...]:
    """Return ordered top-level fields from a capability action schema."""
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return ()
    required = {
        str(name) for name in schema.get("required", []) if isinstance(name, str)
    }
    return tuple(
        SchemaField(
            name=str(name),
            schema=_mapping(field_schema),
            required=str(name) in required,
        )
        for name, field_schema in properties.items()
        if isinstance(field_schema, dict)
    )


def schema_default_text(field: SchemaField) -> str:
    """Render a schema default as editable text."""
    if "const" in field.schema:
        value = field.schema["const"]
    elif "default" in field.schema:
        value = field.schema["default"]
    else:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def parse_schema_input(field: SchemaField, raw_value: str) -> tuple[bool, Any]:
    """Parse one form value according to its advertised top-level JSON type.

    Returns:
        A ``(present, value)`` pair. Optional blank fields are omitted.
    """
    if "const" in field.schema:
        return True, field.schema["const"]

    if not raw_value and not field.required:
        if "default" in field.schema:
            return True, field.schema["default"]
        return False, None

    kind = field.kind
    try:
        if kind == "string":
            value: Any = raw_value
        elif kind == "integer":
            if not raw_value:
                raise ValueError("a value is required")
            value = int(raw_value)
        elif kind == "number":
            if not raw_value:
                raise ValueError("a value is required")
            value = float(raw_value)
        elif kind == "boolean":
            lowered = raw_value.strip().lower()
            if lowered not in {"true", "false"}:
                raise ValueError("use true or false")
            value = lowered == "true"
        elif kind in {"object", "array"}:
            value = json.loads(raw_value)
            expected = dict if kind == "object" else list
            if not isinstance(value, expected):
                raise ValueError(f"expected a JSON {kind}")
        elif kind == "null":
            value = None
        else:
            value = json.loads(raw_value)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SchemaInputError(f"{field.name}: {exc}") from exc

    allowed = field.schema.get("enum")
    if isinstance(allowed, list) and value not in allowed:
        rendered = ", ".join(str(item) for item in allowed)
        raise SchemaInputError(f"{field.name}: choose one of {rendered}")
    return True, value


def explicit_run_id(payload: Any, *, max_depth: int = 3) -> str | None:
    """Extract only an explicitly named run identity from a gateway result."""
    if max_depth < 0:
        return None
    if isinstance(payload, dict):
        for key in ("run_id", "runId"):
            value = payload.get(key)
            if value:
                return str(value)
        for value in payload.values():
            run_id = explicit_run_id(value, max_depth=max_depth - 1)
            if run_id:
                return run_id
    elif isinstance(payload, list):
        for value in payload:
            run_id = explicit_run_id(value, max_depth=max_depth - 1)
            if run_id:
                return run_id
    return None
