"""Startup-phase messages (identifier-less special messages)."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Self

from pygwire.constants import ProtocolVersion

from ._base import SpecialMessage, _read_cstring
from ._registry import STARTUP_REGISTRY

_INT32 = struct.Struct("!I")


@STARTUP_REGISTRY.register(version_code=ProtocolVersion.V3_0)
@STARTUP_REGISTRY.register(version_code=ProtocolVersion.V3_2)
@dataclass(slots=True)
class StartupMessage(SpecialMessage):
    """StartupMessage — initial connection packet (Protocol 3.0 & 3.2).

    Contains key-value parameters (user, database, options, etc.)
    terminated by a final null byte.  The ``encode()`` method returns
    the full payload including the Int32 version code.

    Note: The message format is identical in v3.0 and v3.2. Protocol version
    3.2 (PostgreSQL 18+) only differs in CancelRequest and BackendKeyData
    messages which support variable-length secret keys.
    """

    params: dict[str, str] = field(default_factory=dict)
    protocol_version: int = ProtocolVersion.V3_0

    def encode(self) -> bytes:
        buf = bytearray(_INT32.pack(self.protocol_version))
        for key, value in self.params.items():
            buf.extend(key.encode("utf-8"))
            buf.append(0)
            buf.extend(value.encode("utf-8"))
            buf.append(0)
        buf.append(0)
        return bytes(buf)

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        (protocol_version,) = _INT32.unpack_from(payload, 0)
        offset = 4
        params: dict[str, str] = {}
        while offset < len(payload) and payload[offset] != 0:
            key, offset = _read_cstring(payload, offset)
            val, offset = _read_cstring(payload, offset)
            params[key] = val
        return cls(params=params, protocol_version=protocol_version)


@STARTUP_REGISTRY.register(version_code=ProtocolVersion.SSL_REQUEST)
@dataclass(slots=True)
class SSLRequest(SpecialMessage):
    """SSLRequest — asks if the server supports SSL.

    Payload is just the Int32 request code (80877103).
    """

    def encode(self) -> bytes:
        return _INT32.pack(ProtocolVersion.SSL_REQUEST)

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()


@STARTUP_REGISTRY.register(version_code=ProtocolVersion.GSSENC_REQUEST)
@dataclass(slots=True)
class GSSEncRequest(SpecialMessage):
    """GSSEncRequest — asks if the server supports GSS encryption.

    Payload is just the Int32 request code (80877104).
    """

    def encode(self) -> bytes:
        return _INT32.pack(ProtocolVersion.GSSENC_REQUEST)

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()


@STARTUP_REGISTRY.register(version_code=ProtocolVersion.CANCEL_REQUEST)
@dataclass(slots=True)
class CancelRequest(SpecialMessage):
    """CancelRequest — asks the server to cancel a running query.

    Protocol 3.0 (PG 14-17): secret_key is 4 bytes.
    Protocol 3.2 (PG 18+):   secret_key is variable length (up to 256 bytes).
    The ``encode()`` returns the cancel request code + process_id + secret_key.
    """

    process_id: int = 0
    secret_key: bytes = b""

    def encode(self) -> bytes:
        return (
            _INT32.pack(ProtocolVersion.CANCEL_REQUEST)
            + _INT32.pack(self.process_id)
            + self.secret_key
        )

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        (pid,) = _INT32.unpack_from(payload, 4)
        key = bytes(payload[8:])
        return cls(process_id=pid, secret_key=key)
