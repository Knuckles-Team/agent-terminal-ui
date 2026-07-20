"""Textual command-palette provider backed by the live capability catalog."""

from __future__ import annotations

from textual.command import DiscoveryHit, Hit, Hits, Provider

from agent_terminal_ui.capabilities import CapabilityCatalog, CapabilityDescriptor


class CapabilityCommandProvider(Provider):
    """Expose gateway capabilities beside Textual's built-in app commands."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._catalog: CapabilityCatalog | None = None
        self._error: str | None = None

    async def startup(self) -> None:
        """Load one catalog snapshot when the command palette opens."""
        try:
            self._catalog = await self.app.agent_client.list_capabilities(
                include_actions=True
            )
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"

    def _open(self, capability_id: str | None = None) -> None:
        opener = getattr(self.app, "open_capability_palette", None)
        if callable(opener):
            opener(capability_id=capability_id)

    @staticmethod
    def _help(capability: CapabilityDescriptor) -> str:
        availability = capability.availability
        detail = capability.one_line or capability.id
        if availability.is_available:
            if availability.readiness == "cold":
                return f"Available with cold start. {detail}"
            return f"Available. {detail}"
        return f"{availability.status.title()}: {availability.explanation}. {detail}"

    async def search(self, query: str) -> Hits:
        """Fuzzy-search IDs, titles, actions, intents, and tags."""
        if self._catalog is None:
            if self._error:
                matcher = self.matcher(query)
                candidate = "Capabilities unavailable"
                score = matcher.match(candidate)
                if score > 0:
                    yield Hit(
                        score,
                        matcher.highlight(candidate),
                        lambda: self.app.notify(
                            f"Capability catalog unavailable: {self._error}",
                            severity="warning",
                        ),
                        help="The gateway catalog could not be loaded.",
                    )
            return

        matcher = self.matcher(query)
        for capability in self._catalog.capabilities:
            score = matcher.match(capability.search_text)
            if score <= 0:
                continue
            display = (
                f"Capability: {capability.title} "
                f"[{capability.availability.display_status}]"
            )
            yield Hit(
                score,
                display,
                lambda capability_id=capability.id: self._open(capability_id),
                text=capability.search_text,
                help=self._help(capability),
            )

    async def discover(self) -> Hits:
        """Offer a stable entry point before the user starts searching."""
        yield DiscoveryHit(
            "Browse live capabilities",
            self._open,
            help="Search schemas, preflight side effects, and invoke safely.",
        )
