"""Error messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self

from pygwire.constants import BackendMessageType

from ._base import BackendMessage, _decode_field_messages, _encode_field_messages, register


@register(BackendMessageType.ERROR_RESPONSE)
@dataclass(slots=True)
class ErrorResponse(BackendMessage):
    """ErrorResponse ('E') — structured error from the server.

    Fields are keyed by single-character codes:
        'S' — Severity (localized)
        'V' — Severity (always English)
        'C' — SQLSTATE code
        'M' — Message
        'D' — Detail
        'H' — Hint
        'P' — Position
        'p' — Internal position
        'q' — Internal query
        'W' — Where
        's' — Schema name
        't' — Table name
        'c' — Column name
        'd' — Data type name
        'n' — Constraint name
        'F' — File
        'L' — Line
        'R' — Routine
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
