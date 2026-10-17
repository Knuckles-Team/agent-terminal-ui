"""Authenticated host log adapter and bounded terminal subscription."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import Any, Protocol

import httpx


@dataclass(frozen=True)
class HostLaunchReceipt:
    """Server binding facts; only the reader that obtained them accepts them."""

    version: int
    log_ref: str
    host_instance: str
    workspace: str
    tenant: str
    principal: str
    session_ref: str
    policy_revision: str
    grant_revision: str
    expires_at_ms: int
    interface_mode: str
    web_logs: bool
    ready: bool

    @classmethod
    def from_payload(cls, payload: Any) -> HostLaunchReceipt:
        if not isinstance(payload, dict) or set(payload) != {
            f.name for f in fields(cls)
        }:
            raise ValueError("invalid host receipt shape")
        receipt = cls(**payload)
        text_fields = (
            receipt.log_ref,
            receipt.host_instance,
            receipt.workspace,
            receipt.tenant,
            receipt.principal,
            receipt.session_ref,
            receipt.policy_revision,
            receipt.grant_revision,
        )
        if any(
            type(value) is not str or not value or len(value) > 4096
            for value in text_fields
        ):
            raise ValueError("invalid host receipt binding")
        if (
            type(receipt.version) is not int
            or receipt.version != 1
            or type(receipt.expires_at_ms) is not int
            or type(receipt.ready) is not bool
            or type(receipt.web_logs) is not bool
            or receipt.interface_mode not in {"terminal", "web", "both"}
            or len(receipt.log_ref) > 128
        ):
            raise ValueError("invalid host receipt version or preference")
        return receipt


RETENTION_GAP = (
    "Host log history gap: the resume position is no longer retained. "
    "Fresh admission is required."
)


class HostLogRetentionGap(Exception):
    """The server refused a position that is no longer retained."""


@dataclass(frozen=True)
class HostLogRecord:
    host_instance: str
    sequence: int
    request: str
    timestamp: float
    severity: str
    message: str

    def display(self) -> str:
        return (
            f"[{self.timestamp} {self.severity} host={self.host_instance} "
            f"seq={self.sequence} request={self.request}] {self.message}"
        )


@dataclass(frozen=True)
class HostLogBatch:
    records: tuple[HostLogRecord, ...]
    cursor: str | None
    gap: bool


class HostLogReader(Protocol):
    def accepts(self, receipt: HostLaunchReceipt) -> bool: ...

    async def read(
        self, log_ref: str, *, cursor: str | None, limit: int
    ) -> HostLogBatch: ...


class AuthenticatedHostLogReader:
    """Borrow a preconfigured authenticated HTTP client; never own credentials."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._receipt: HostLaunchReceipt | None = None
        self._endpoint = str(client.base_url)

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        if str(self._client.base_url) != self._endpoint:
            raise PermissionError("host binding changed")
        async with asyncio.timeout(1):
            async with self._client.stream(
                "POST", path, json=body, follow_redirects=False
            ) as response:
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > 2 * 1024 * 1024:
                        raise ValueError("host log response limit")
                    data.extend(chunk)
                if response.status_code == 409 and json.loads(data) == {
                    "detail": "retention_gap"
                }:
                    raise HostLogRetentionGap(RETENTION_GAP)
                response.raise_for_status()
        return json.loads(data)

    async def bind(self) -> HostLaunchReceipt:
        self._receipt = None
        receipt = HostLaunchReceipt.from_payload(
            await self._post("host/logs/reference", {})
        )
        self._receipt = receipt
        if not self.accepts(receipt):
            self._receipt = None
            raise PermissionError("host log handoff unavailable")
        return receipt

    def accepts(self, receipt: HostLaunchReceipt) -> bool:
        return (
            receipt is self._receipt
            and str(self._client.base_url) == self._endpoint
            and receipt.ready
            and receipt.web_logs
            and receipt.interface_mode in {"terminal", "both"}
            and receipt.expires_at_ms > int(time.time() * 1000)
        )

    async def read(
        self, log_ref: str, *, cursor: str | None, limit: int
    ) -> HostLogBatch:
        receipt = self._receipt
        if receipt is None or not self.accepts(receipt) or log_ref != receipt.log_ref:
            raise PermissionError("host log binding refused")
        if type(limit) is not int or not 1 <= limit <= 128:
            raise ValueError("host log batch limit")
        try:
            payload = await self._post(
                "host/logs/read",
                {"version": 2, "log_ref": log_ref, "cursor": cursor, "limit": limit},
            )
            if not self.accepts(receipt):
                raise PermissionError("host log session expired")
            return _batch(payload, limit)
        except Exception:
            self._receipt = None
            raise


def _batch(payload: Any, limit: int) -> HostLogBatch:
    if (
        not isinstance(payload, dict)
        or set(payload) != {"version", "records", "cursor", "gap"}
        or type(payload["version"]) is not int
        or payload["version"] != 2
    ):
        raise ValueError("invalid host log batch")
    rows, cursor, gap = payload["records"], payload["cursor"], payload["gap"]
    if not isinstance(rows, list) or len(rows) > limit or type(gap) is not bool:
        raise ValueError("invalid host log bounds")
    if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 1024):
        raise ValueError("invalid host log cursor")
    records = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            f.name for f in fields(HostLogRecord)
        }:
            raise ValueError("invalid host log record")
        for key, maximum in (
            ("host_instance", 128),
            ("request", 1024),
            ("severity", 32),
            ("message", 16384),
        ):
            if type(row[key]) is not str or len(row[key].encode()) > maximum:
                raise ValueError("invalid host log text")
        if (
            not row["host_instance"]
            or not row["severity"]
            or type(row["sequence"]) is not int
            or not 1 <= row["sequence"] <= 2**63 - 1
            or type(row["timestamp"]) not in (int, float)
            or not math.isfinite(row["timestamp"])
            or row["timestamp"] < 0
        ):
            raise ValueError("invalid host log metadata")
        clean: dict[str, Any] = {
            key: _literal(value, multiline=key == "message")
            if isinstance(value, str)
            else value
            for key, value in row.items()
        }
        records.append(HostLogRecord(**clean))
    return HostLogBatch(tuple(records), cursor, gap)


def _literal(value: str, *, multiline: bool) -> str:
    return "".join(
        c
        for c in value
        if (multiline and c in "\n\t") or (ord(c) >= 32 and not 127 <= ord(c) <= 159)
    )


class HostLogSubscription:
    """One read in flight; retain only the last acknowledged opaque cursor."""

    def __init__(
        self,
        reader: HostLogReader,
        receipt: HostLaunchReceipt,
        display: Callable[[HostLogBatch], None],
        refused: Callable[[], None],
        retention_gap: Callable[[], None],
    ) -> None:
        self.reader, self.receipt = reader, receipt
        self._display, self._refused = display, refused
        self._retention_gap = retention_gap
        self._task: asyncio.Task | None = None
        self._cursor: str | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            while self.reader.accepts(self.receipt):
                async with asyncio.timeout(1):
                    batch = await self.reader.read(
                        self.receipt.log_ref, cursor=self._cursor, limit=128
                    )
                self._display(batch)
                self._cursor = batch.cursor
                await asyncio.sleep(0.25)
            raise PermissionError("host log handoff expired")
        except asyncio.CancelledError:
            raise
        except HostLogRetentionGap:
            self._cursor = None
            self._retention_gap()
        except Exception:
            self._cursor = None
            self._refused()

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, 5)
            except asyncio.CancelledError:
                pass
            self._task = None
