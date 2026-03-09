"""Notification and status messages."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Self

from pygwire.constants import MessageDirection

from ._base import (
    BackendMessage,
    _decode_field_messages,
    _encode_field_messages,
    _read_cstring,
)
from ._registry import STANDARD_REGISTRY

_INT32 = struct.Struct("!I")
# NotificationResponse ('A')
# ═══════════════════════════════════════════════════════════════════════════


@STANDARD_REGISTRY.register(b"A", direction=MessageDirection.BACKEND)
@dataclass(slots=True)
class NotificationResponse(BackendMessage):
    """NotificationResponse ('A') — asynchronous NOTIFY event."""

    process_id: int = 0
    channel: str = ""
    payload: str = ""

    def encode(self) -> bytes:
        return (
            _INT32.pack(self.process_id)
            + self.channel.encode("utf-8")
            + b"\x00"
            + self.payload.encode("utf-8")
            + b"\x00"
        )

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        (pid,) = _INT32.unpack_from(payload)
        channel, offset = _read_cstring(payload, 4)
        pl, _ = _read_cstring(payload, offset)
        return cls(process_id=pid, channel=channel, payload=pl)


# ═══════════════════════════════════════════════════════════════════════════
# NoticeResponse ('N')
# ═══════════════════════════════════════════════════════════════════════════


@STANDARD_REGISTRY.register(b"N", direction=MessageDirection.BACKEND)
@dataclass(slots=True)
class NoticeResponse(BackendMessage):
    """NoticeResponse ('N') — non-fatal notice from the server.

    Uses the same field format as ErrorResponse.
    """

    fields: dict[str, str] = field(default_factory=dict)

    @property
    def severity(self) -> str:
        return self.fields.get("S", "")

    @property
    def code(self) -> str:
        return self.fields.get("C", "")

    @property
    def message(self) -> str:
        return self.fields.get("M", "")

    def encode(self) -> bytes:
        return _encode_field_messages(self.fields)

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls(fields=_decode_field_messages(payload))


# ═══════════════════════════════════════════════════════════════════════════
# ParameterStatus ('S')
# ═══════════════════════════════════════════════════════════════════════════


@STANDARD_REGISTRY.register(b"S", direction=MessageDirection.BACKEND)
@dataclass(slots=True)
class ParameterStatus(BackendMessage):
    """ParameterStatus ('S') — reports a runtime parameter value."""

    name: str = ""
    value: str = ""

    def encode(self) -> bytes:
        return self.name.encode("utf-8") + b"\x00" + self.value.encode("utf-8") + b"\x00"

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        name, offset = _read_cstring(payload, 0)
        value, _ = _read_cstring(payload, offset)
        return cls(name=name, value=value)
