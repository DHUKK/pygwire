"""Extended query protocol messages."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Self

from pygwire.constants import ConnectionPhase, MessageDirection

from ._base import BackendMessage, FrontendMessage, _read_cstring
from ._registry import STANDARD_REGISTRY

# ---------------------------------------------------------------------------
# Struct helpers (pre-compiled for hot-path parsing)
# ---------------------------------------------------------------------------
_INT32 = struct.Struct("!I")  # unsigned 32-bit, network byte order
_INT16 = struct.Struct("!H")  # unsigned 16-bit, network byte order
_SINT32 = struct.Struct("!i")  # signed 32-bit (NULL parameter sentinel -1)


# ═══════════════════════════════════════════════════════════════════════════
# Frontend messages
# ═══════════════════════════════════════════════════════════════════════════


@STANDARD_REGISTRY.register(
    b"P",
    direction=MessageDirection.FRONTEND,
    phases=frozenset({ConnectionPhase.READY, ConnectionPhase.EXTENDED_QUERY}),
)
@dataclass(slots=True)
class Parse(FrontendMessage):
    """Parse ('P') — create a prepared statement.

    Format:
        String   — destination statement name (empty = unnamed)
        String   — query string
        Int16    — number of parameter type OIDs
        Int32[n] — parameter type OIDs (0 = unspecified)
    """

    statement: str = ""
    query: str = ""
    param_types: list[int] = field(default_factory=list)

    def encode(self) -> bytes:
        buf = bytearray()
        buf.extend(self.statement.encode("utf-8"))
        buf.append(0)
        buf.extend(self.query.encode("utf-8"))
        buf.append(0)
        buf.extend(_INT16.pack(len(self.param_types)))
        for oid in self.param_types:
            buf.extend(_INT32.pack(oid))
        return bytes(buf)

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        statement, offset = _read_cstring(payload, 0)
        query, offset = _read_cstring(payload, offset)
        (num_params,) = _INT16.unpack_from(payload, offset)
        offset += 2
        param_types: list[int] = []
        for _ in range(num_params):
            (oid,) = _INT32.unpack_from(payload, offset)
            param_types.append(oid)
            offset += 4
        return cls(statement=statement, query=query, param_types=param_types)


@STANDARD_REGISTRY.register(
    b"B",
    direction=MessageDirection.FRONTEND,
    phases=frozenset({ConnectionPhase.READY, ConnectionPhase.EXTENDED_QUERY}),
)
@dataclass(slots=True)
class Bind(FrontendMessage):
    """Bind ('B') — bind parameters to a prepared statement, creating a portal.

    Format:
        String       — destination portal name (empty = unnamed)
        String       — source statement name (empty = unnamed)
        Int16        — number of parameter format codes
        Int16[n]     — parameter format codes (0=text, 1=binary)
        Int16        — number of parameter values
        For each parameter:
            Int32    — length (-1 = NULL)
            Byte[n]  — value (absent if NULL)
        Int16        — number of result column format codes
        Int16[n]     — result column format codes (0=text, 1=binary)
    """

    portal: str = ""
    statement: str = ""
    param_formats: list[int] = field(default_factory=list)
    param_values: list[bytes | None] = field(default_factory=list)
    result_formats: list[int] = field(default_factory=list)

    def encode(self) -> bytes:
        buf = bytearray()
        # Portal and statement names
        buf.extend(self.portal.encode("utf-8"))
        buf.append(0)
        buf.extend(self.statement.encode("utf-8"))
        buf.append(0)
        # Parameter format codes
        buf.extend(_INT16.pack(len(self.param_formats)))
        for fmt in self.param_formats:
            buf.extend(_INT16.pack(fmt))
        # Parameter values
        buf.extend(_INT16.pack(len(self.param_values)))
        for val in self.param_values:
            if val is None:
                buf.extend(_SINT32.pack(-1))
            else:
                buf.extend(_INT32.pack(len(val)))
                buf.extend(val)
        # Result format codes
        buf.extend(_INT16.pack(len(self.result_formats)))
        for fmt in self.result_formats:
            buf.extend(_INT16.pack(fmt))
        return bytes(buf)

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        portal, offset = _read_cstring(payload, 0)
        statement, offset = _read_cstring(payload, offset)
        # Parameter format codes
        (num_fmt,) = _INT16.unpack_from(payload, offset)
        offset += 2
        param_formats: list[int] = []
        for _ in range(num_fmt):
            (fmt,) = _INT16.unpack_from(payload, offset)
            param_formats.append(fmt)
            offset += 2
        # Parameter values
        (num_vals,) = _INT16.unpack_from(payload, offset)
        offset += 2
        param_values: list[bytes | None] = []
        for _ in range(num_vals):
            (val_len,) = _SINT32.unpack_from(payload, offset)
            offset += 4
            if val_len == -1:
                param_values.append(None)
            else:
                param_values.append(bytes(payload[offset : offset + val_len]))
                offset += val_len
        # Result format codes
        (num_res_fmt,) = _INT16.unpack_from(payload, offset)
        offset += 2
        result_formats: list[int] = []
        for _ in range(num_res_fmt):
            (fmt,) = _INT16.unpack_from(payload, offset)
            result_formats.append(fmt)
            offset += 2
        return cls(
            portal=portal,
            statement=statement,
            param_formats=param_formats,
            param_values=param_values,
            result_formats=result_formats,
        )


@STANDARD_REGISTRY.register(
    b"D",
    direction=MessageDirection.FRONTEND,
    phases=frozenset({ConnectionPhase.READY, ConnectionPhase.EXTENDED_QUERY}),
)
@dataclass(slots=True)
class Describe(FrontendMessage):
    """Describe ('D') — request description of a statement or portal.

    Format:
        Byte1  — 'S' for statement, 'P' for portal
        String — name (empty = unnamed)
    """

    kind: str = "S"  # 'S' = Statement, 'P' = Portal
    name: str = ""

    def encode(self) -> bytes:
        return self.kind.encode("ascii") + self.name.encode("utf-8") + b"\x00"

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        kind = chr(payload[0])
        name, _ = _read_cstring(payload, 1)
        return cls(kind=kind, name=name)


@STANDARD_REGISTRY.register(
    b"E",
    direction=MessageDirection.FRONTEND,
    phases=frozenset({ConnectionPhase.READY, ConnectionPhase.EXTENDED_QUERY}),
)
@dataclass(slots=True)
class Execute(FrontendMessage):
    """Execute ('E') — execute a portal.

    Format:
        String — portal name (empty = unnamed)
        Int32  — max rows to return (0 = no limit)
    """

    portal: str = ""
    max_rows: int = 0

    def encode(self) -> bytes:
        return self.portal.encode("utf-8") + b"\x00" + _INT32.pack(self.max_rows)

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        portal, offset = _read_cstring(payload, 0)
        (max_rows,) = _INT32.unpack_from(payload, offset)
        return cls(portal=portal, max_rows=max_rows)


@STANDARD_REGISTRY.register(
    b"C",
    direction=MessageDirection.FRONTEND,
    phases=frozenset({ConnectionPhase.READY, ConnectionPhase.EXTENDED_QUERY}),
)
@dataclass(slots=True)
class Close(FrontendMessage):
    """Close ('C') — close a statement or portal.

    Format:
        Byte1  — 'S' for statement, 'P' for portal
        String — name (empty = unnamed)
    """

    kind: str = "S"  # 'S' = Statement, 'P' = Portal
    name: str = ""

    def encode(self) -> bytes:
        return self.kind.encode("ascii") + self.name.encode("utf-8") + b"\x00"

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        kind = chr(payload[0])
        name, _ = _read_cstring(payload, 1)
        return cls(kind=kind, name=name)


@STANDARD_REGISTRY.register(
    b"S",
    direction=MessageDirection.FRONTEND,
    phases=frozenset({ConnectionPhase.READY, ConnectionPhase.EXTENDED_QUERY}),
)
@dataclass(slots=True)
class Sync(FrontendMessage):
    """Sync ('S') — marks the end of an extended query cycle."""

    def encode(self) -> bytes:
        return b""

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()


@STANDARD_REGISTRY.register(
    b"H",
    direction=MessageDirection.FRONTEND,
    phases=frozenset({ConnectionPhase.READY, ConnectionPhase.EXTENDED_QUERY}),
)
@dataclass(slots=True)
class Flush(FrontendMessage):
    """Flush ('H') — request the server to send any pending output."""

    def encode(self) -> bytes:
        return b""

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()


# ═══════════════════════════════════════════════════════════════════════════
# Backend messages
# ═══════════════════════════════════════════════════════════════════════════


@STANDARD_REGISTRY.register(
    b"1",
    direction=MessageDirection.BACKEND,
    phases=frozenset({ConnectionPhase.EXTENDED_QUERY}),
)
@dataclass(slots=True)
class ParseComplete(BackendMessage):
    """ParseComplete ('1')."""

    def encode(self) -> bytes:
        return b""

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()


@STANDARD_REGISTRY.register(
    b"2",
    direction=MessageDirection.BACKEND,
    phases=frozenset({ConnectionPhase.EXTENDED_QUERY}),
)
@dataclass(slots=True)
class BindComplete(BackendMessage):
    """BindComplete ('2')."""

    def encode(self) -> bytes:
        return b""

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()


@STANDARD_REGISTRY.register(
    b"3",
    direction=MessageDirection.BACKEND,
    phases=frozenset({ConnectionPhase.EXTENDED_QUERY}),
)
@dataclass(slots=True)
class CloseComplete(BackendMessage):
    """CloseComplete ('3')."""

    def encode(self) -> bytes:
        return b""

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()


@STANDARD_REGISTRY.register(
    b"n",
    direction=MessageDirection.BACKEND,
    phases=frozenset({ConnectionPhase.EXTENDED_QUERY}),
)
@dataclass(slots=True)
class NoData(BackendMessage):
    """NoData ('n')."""

    def encode(self) -> bytes:
        return b""

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()


@STANDARD_REGISTRY.register(
    b"s",
    direction=MessageDirection.BACKEND,
    phases=frozenset({ConnectionPhase.EXTENDED_QUERY}),
)
@dataclass(slots=True)
class PortalSuspended(BackendMessage):
    """PortalSuspended ('s')."""

    def encode(self) -> bytes:
        return b""

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()


@STANDARD_REGISTRY.register(
    b"t",
    direction=MessageDirection.BACKEND,
    phases=frozenset({ConnectionPhase.EXTENDED_QUERY}),
)
@dataclass(slots=True)
class ParameterDescription(BackendMessage):
    """ParameterDescription ('t') — OIDs of parameters in a prepared statement."""

    type_oids: list[int] = field(default_factory=list)

    def encode(self) -> bytes:
        buf = bytearray(_INT16.pack(len(self.type_oids)))
        for oid in self.type_oids:
            buf.extend(_INT32.pack(oid))
        return bytes(buf)

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        (count,) = _INT16.unpack_from(payload)
        oids: list[int] = []
        offset = 2
        for _ in range(count):
            (oid,) = _INT32.unpack_from(payload, offset)
            oids.append(oid)
            offset += 4
        return cls(type_oids=oids)
