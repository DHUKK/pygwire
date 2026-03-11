"""COPY protocol messages."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Self

from pygwire.constants import ConnectionPhase, MessageDirection

from ._base import (
    BackendMessage,
    CommonMessage,
    FrontendMessage,
    _read_cstring,
)
from ._registry import STANDARD_REGISTRY

_INT16 = struct.Struct("!H")


@STANDARD_REGISTRY.register(
    b"d",
    direction=MessageDirection.FRONTEND,
    phases=frozenset({ConnectionPhase.COPY_IN, ConnectionPhase.COPY_OUT}),
)
@STANDARD_REGISTRY.register(
    b"d",
    direction=MessageDirection.BACKEND,
    phases=frozenset({ConnectionPhase.COPY_IN, ConnectionPhase.COPY_OUT}),
)
@dataclass(slots=True)
class CopyData(CommonMessage):
    """CopyData ('d') — a chunk of COPY data (used by both Frontend and Backend)."""

    data: bytes = b""

    def encode(self) -> bytes:
        return self.data

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls(data=bytes(payload))


@STANDARD_REGISTRY.register(
    b"c",
    direction=MessageDirection.FRONTEND,
    phases=frozenset({ConnectionPhase.COPY_IN, ConnectionPhase.COPY_OUT}),
)
@STANDARD_REGISTRY.register(
    b"c",
    direction=MessageDirection.BACKEND,
    phases=frozenset({ConnectionPhase.COPY_IN, ConnectionPhase.COPY_OUT}),
)
@dataclass(slots=True)
class CopyDone(CommonMessage):
    """CopyDone ('c') — signals end of COPY data (used by both Frontend and Backend)."""

    def encode(self) -> bytes:
        return b""

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()


# ═══════════════════════════════════════════════════════════════════════════
# Frontend messages
# ═══════════════════════════════════════════════════════════════════════════


@STANDARD_REGISTRY.register(
    b"f",
    direction=MessageDirection.FRONTEND,
    phases=frozenset({ConnectionPhase.COPY_IN}),
)
@dataclass(slots=True)
class CopyFail(FrontendMessage):
    """CopyFail ('f') — client signals COPY failure with an error message."""

    error_message: str = ""

    def encode(self) -> bytes:
        return self.error_message.encode("utf-8") + b"\x00"

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        msg, _ = _read_cstring(payload, 0)
        return cls(error_message=msg)


# ═══════════════════════════════════════════════════════════════════════════
# Backend messages
# ═══════════════════════════════════════════════════════════════════════════


def _decode_copy_response(payload: memoryview) -> tuple[int, list[int]]:
    """Shared decoder for CopyInResponse and CopyOutResponse."""
    overall_format = payload[0]
    (num_cols,) = _INT16.unpack_from(payload, 1)
    col_formats: list[int] = []
    offset = 3
    for _ in range(num_cols):
        (fmt,) = _INT16.unpack_from(payload, offset)
        col_formats.append(fmt)
        offset += 2
    return overall_format, col_formats


def _encode_copy_response(overall_format: int, col_formats: list[int]) -> bytes:
    buf = bytearray()
    buf.append(overall_format)
    buf.extend(_INT16.pack(len(col_formats)))
    for fmt in col_formats:
        buf.extend(_INT16.pack(fmt))
    return bytes(buf)


@STANDARD_REGISTRY.register(
    b"G",
    direction=MessageDirection.BACKEND,
    phases=frozenset({ConnectionPhase.SIMPLE_QUERY, ConnectionPhase.EXTENDED_QUERY}),
)
@dataclass(slots=True)
class CopyInResponse(BackendMessage):
    """CopyInResponse ('G') — server is ready to accept COPY data."""

    overall_format: int = 0
    col_formats: list[int] = field(default_factory=list)

    def encode(self) -> bytes:
        return _encode_copy_response(self.overall_format, self.col_formats)

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        fmt, cols = _decode_copy_response(payload)
        return cls(overall_format=fmt, col_formats=cols)


@STANDARD_REGISTRY.register(
    b"H",
    direction=MessageDirection.BACKEND,
    phases=frozenset({ConnectionPhase.SIMPLE_QUERY, ConnectionPhase.EXTENDED_QUERY}),
)
@dataclass(slots=True)
class CopyOutResponse(BackendMessage):
    """CopyOutResponse ('H') — server is about to send COPY data."""

    overall_format: int = 0
    col_formats: list[int] = field(default_factory=list)

    def encode(self) -> bytes:
        return _encode_copy_response(self.overall_format, self.col_formats)

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        fmt, cols = _decode_copy_response(payload)
        return cls(overall_format=fmt, col_formats=cols)
