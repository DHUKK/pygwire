"""Miscellaneous messages (BackendKeyData, FunctionCall, etc.)."""

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
_SINT32 = struct.Struct("!i")  # signed 32-bit (used for NULL sentinel -1)


# ═══════════════════════════════════════════════════════════════════════════
# BackendKeyData ('K') — Protocol 3.0 & 3.2
# ═══════════════════════════════════════════════════════════════════════════


@STANDARD_REGISTRY.register(
    b"K",
    direction=MessageDirection.BACKEND,
    phases=frozenset({ConnectionPhase.INITIALIZATION}),
)
@dataclass(slots=True)
class BackendKeyData(BackendMessage):
    """Secret key data sent after authentication.

    Protocol 3.0 (PG 14-17): secret_key is always 4 bytes.
    Protocol 3.2 (PG 18+):   secret_key is variable length (up to 256 bytes).
    The decoder reads the process_id (4 bytes) and treats the *entire*
    remainder of the payload as the secret key.
    """

    process_id: int = 0
    secret_key: bytes = b""

    def encode(self) -> bytes:
        return _INT32.pack(self.process_id) + self.secret_key

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        (pid,) = _INT32.unpack_from(payload)
        key = bytes(payload[4:])
        return cls(process_id=pid, secret_key=key)


# ═══════════════════════════════════════════════════════════════════════════
# FunctionCall ('F') and FunctionCallResponse ('V')
# ═══════════════════════════════════════════════════════════════════════════


@STANDARD_REGISTRY.register(
    b"F",
    direction=MessageDirection.FRONTEND,
    phases=frozenset({ConnectionPhase.READY}),
)
@dataclass(slots=True)
class FunctionCall(FrontendMessage):
    """FunctionCall ('F') — call a server-side function (legacy protocol).

    Format:
        Int32    — function OID
        Int16    — number of argument format codes
        Int16[n] — argument format codes (0=text, 1=binary)
        Int16    — number of arguments
        For each argument:
            Int32  — length (-1 = NULL)
            Byte[n] — value (absent if NULL)
        Int16    — result format code (0=text, 1=binary)
    """

    function_oid: int = 0
    arg_formats: list[int] = field(default_factory=list)
    arguments: list[bytes | None] = field(default_factory=list)
    result_format: int = 0

    def encode(self) -> bytes:
        buf = bytearray()
        buf.extend(_INT32.pack(self.function_oid))
        buf.extend(_INT16.pack(len(self.arg_formats)))
        for fmt in self.arg_formats:
            buf.extend(_INT16.pack(fmt))
        buf.extend(_INT16.pack(len(self.arguments)))
        for arg in self.arguments:
            if arg is None:
                buf.extend(_SINT32.pack(-1))
            else:
                buf.extend(_INT32.pack(len(arg)))
                buf.extend(arg)
        buf.extend(_INT16.pack(self.result_format))
        return bytes(buf)

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        (func_oid,) = _INT32.unpack_from(payload)
        offset = 4
        (num_fmt,) = _INT16.unpack_from(payload, offset)
        offset += 2
        arg_formats: list[int] = []
        for _ in range(num_fmt):
            (fmt,) = _INT16.unpack_from(payload, offset)
            arg_formats.append(fmt)
            offset += 2
        (num_args,) = _INT16.unpack_from(payload, offset)
        offset += 2
        arguments: list[bytes | None] = []
        for _ in range(num_args):
            (arg_len,) = _SINT32.unpack_from(payload, offset)
            offset += 4
            if arg_len == -1:
                arguments.append(None)
            else:
                arguments.append(bytes(payload[offset : offset + arg_len]))
                offset += arg_len
        (result_format,) = _INT16.unpack_from(payload, offset)
        return cls(
            function_oid=func_oid,
            arg_formats=arg_formats,
            arguments=arguments,
            result_format=result_format,
        )


@STANDARD_REGISTRY.register(
    b"V",
    direction=MessageDirection.BACKEND,
    phases=frozenset({ConnectionPhase.READY}),
)
@dataclass(slots=True)
class FunctionCallResponse(BackendMessage):
    """FunctionCallResponse ('V') — result of a function call."""

    result: bytes | None = None

    def encode(self) -> bytes:
        if self.result is None:
            return _SINT32.pack(-1)
        return _INT32.pack(len(self.result)) + self.result

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        (length,) = _SINT32.unpack_from(payload)
        if length == -1:
            return cls(result=None)
        return cls(result=bytes(payload[4 : 4 + length]))


# ═══════════════════════════════════════════════════════════════════════════
# Terminate ('X')
# ═══════════════════════════════════════════════════════════════════════════


@STANDARD_REGISTRY.register(b"X", direction=MessageDirection.FRONTEND)
@dataclass(slots=True)
class Terminate(FrontendMessage):
    """Terminate ('X') — close the connection."""

    def encode(self) -> bytes:
        return b""

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()


# ═══════════════════════════════════════════════════════════════════════════
# NegotiateProtocolVersion ('v')
# ═══════════════════════════════════════════════════════════════════════════


@STANDARD_REGISTRY.register(b"v", direction=MessageDirection.BACKEND)
@dataclass(slots=True)
class NegotiateProtocolVersion(BackendMessage):
    """NegotiateProtocolVersion ('v') — server cannot support requested protocol."""

    newest_minor: int = 0
    unrecognized: list[str] = field(default_factory=list)

    def encode(self) -> bytes:
        buf = bytearray(_INT32.pack(self.newest_minor))
        buf.extend(_INT32.pack(len(self.unrecognized)))
        for opt in self.unrecognized:
            buf.extend(opt.encode("utf-8"))
            buf.append(0)
        return bytes(buf)

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        (newest,) = _INT32.unpack_from(payload)
        (count,) = _INT32.unpack_from(payload, 4)
        offset = 8
        opts: list[str] = []
        for _ in range(count):
            opt, offset = _read_cstring(payload, offset)
            opts.append(opt)
        return cls(newest_minor=newest, unrecognized=opts)
