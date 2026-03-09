"""Simple query protocol messages."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Self

from pygwire.constants import (
    MessageDirection,
    TransactionStatus,
)

from ._base import BackendMessage, FrontendMessage, _read_cstring
from ._registry import STANDARD_REGISTRY

# ---------------------------------------------------------------------------
# Struct helpers (pre-compiled for hot-path parsing)
# ---------------------------------------------------------------------------
_INT32 = struct.Struct("!I")  # unsigned 32-bit, network byte order
_INT16 = struct.Struct("!H")  # unsigned 16-bit, network byte order
_SINT32 = struct.Struct("!i")  # signed 32-bit (used for NULL sentinel -1)


# ═══════════════════════════════════════════════════════════════════════════
# Frontend: Query ('Q')
# ═══════════════════════════════════════════════════════════════════════════


@STANDARD_REGISTRY.register(
    b"Q", direction=MessageDirection.FRONTEND
)  # No phase restriction - state machine validates
@dataclass(slots=True)
class Query(FrontendMessage):
    """Query ('Q') — simple query containing a SQL string."""

    query_string: str = ""

    def encode(self) -> bytes:
        return self.query_string.encode("utf-8") + b"\x00"

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        text, _ = _read_cstring(payload, 0)
        return cls(query_string=text)


# ═══════════════════════════════════════════════════════════════════════════
# Backend: RowDescription ('T')
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(slots=True)
class FieldDescription:
    """Descriptor for a single column in a RowDescription."""

    name: str = ""
    table_oid: int = 0
    column_attr: int = 0
    type_oid: int = 0
    type_size: int = 0
    type_modifier: int = 0
    format_code: int = 0  # 0 = text, 1 = binary


@STANDARD_REGISTRY.register(b"T", direction=MessageDirection.BACKEND)
@dataclass(slots=True)
class RowDescription(BackendMessage):
    """RowDescription ('T') — describes the columns in upcoming DataRow messages."""

    fields: list[FieldDescription] = field(default_factory=list)

    def encode(self) -> bytes:
        buf = bytearray(_INT16.pack(len(self.fields)))
        for f in self.fields:
            buf.extend(f.name.encode("utf-8"))
            buf.append(0)
            buf.extend(
                struct.pack(
                    "!IhIhih",
                    f.table_oid,
                    f.column_attr,
                    f.type_oid,
                    f.type_size,
                    f.type_modifier,
                    f.format_code,
                )
            )
        return bytes(buf)

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        (num_fields,) = _INT16.unpack_from(payload)
        offset = 2
        fields: list[FieldDescription] = []
        for _ in range(num_fields):
            name, offset = _read_cstring(payload, offset)
            (table_oid, col_attr, type_oid, type_size, type_mod, fmt) = struct.unpack_from(
                "!IhIhih", payload, offset
            )
            offset += 18  # 4+2+4+2+4+2
            fields.append(
                FieldDescription(
                    name=name,
                    table_oid=table_oid,
                    column_attr=col_attr,
                    type_oid=type_oid,
                    type_size=type_size,
                    type_modifier=type_mod,
                    format_code=fmt,
                )
            )
        return cls(fields=fields)


# ═══════════════════════════════════════════════════════════════════════════
# Backend: DataRow ('D')
# ═══════════════════════════════════════════════════════════════════════════


@STANDARD_REGISTRY.register(b"D", direction=MessageDirection.BACKEND)
@dataclass(slots=True)
class DataRow(BackendMessage):
    """DataRow ('D') — a single row of query results.

    Each column value is ``bytes`` or ``None`` (SQL NULL).
    """

    columns: list[bytes | None] = field(default_factory=list)

    def encode(self) -> bytes:
        buf = bytearray(_INT16.pack(len(self.columns)))
        for col in self.columns:
            if col is None:
                buf.extend(_SINT32.pack(-1))
            else:
                buf.extend(_INT32.pack(len(col)))
                buf.extend(col)
        return bytes(buf)

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        (num_cols,) = _INT16.unpack_from(payload)
        offset = 2
        columns: list[bytes | None] = []
        for _ in range(num_cols):
            (col_len,) = _SINT32.unpack_from(payload, offset)
            offset += 4
            if col_len == -1:
                columns.append(None)
            else:
                columns.append(bytes(payload[offset : offset + col_len]))
                offset += col_len
        return cls(columns=columns)


# ═══════════════════════════════════════════════════════════════════════════
# Backend: CommandComplete ('C')
# ═══════════════════════════════════════════════════════════════════════════


@STANDARD_REGISTRY.register(b"C", direction=MessageDirection.BACKEND)
@dataclass(slots=True)
class CommandComplete(BackendMessage):
    """CommandComplete ('C') — the command tag (e.g. 'SELECT 42')."""

    tag: str = ""

    def encode(self) -> bytes:
        return self.tag.encode("utf-8") + b"\x00"

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        tag, _ = _read_cstring(payload, 0)
        return cls(tag=tag)


# ═══════════════════════════════════════════════════════════════════════════
# Backend: ReadyForQuery ('Z')
# ═══════════════════════════════════════════════════════════════════════════


@STANDARD_REGISTRY.register(
    b"Z", direction=MessageDirection.BACKEND
)  # Valid in many phases, no restriction
@dataclass(slots=True)
class ReadyForQuery(BackendMessage):
    """ReadyForQuery ('Z') — server is ready for a new query cycle."""

    status: TransactionStatus = TransactionStatus.IDLE

    def encode(self) -> bytes:
        return self.status.value.encode("ascii")

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls(status=TransactionStatus(chr(payload[0])))


# ═══════════════════════════════════════════════════════════════════════════
# Backend: EmptyQueryResponse ('I')
# ═══════════════════════════════════════════════════════════════════════════


@STANDARD_REGISTRY.register(b"I", direction=MessageDirection.BACKEND)
@dataclass(slots=True)
class EmptyQueryResponse(BackendMessage):
    """EmptyQueryResponse ('I')."""

    def encode(self) -> bytes:
        return b""

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()
