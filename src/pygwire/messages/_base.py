"""Base PGMessage class, registry, and common message types."""

from __future__ import annotations

import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar, Self

from pygwire.constants import BackendMessageType, FrontendMessageType


class PygwireError(Exception):
    """Base exception for all Pygwire errors."""


class ProtocolError(PygwireError):
    """Raised when protocol framing or content is invalid."""


# ---------------------------------------------------------------------------
# Message registry (internal only)
# ---------------------------------------------------------------------------
# Maps a single-byte identifier to the message class that handles it.
# Populated by the @register decorator.

_BACKEND_REGISTRY: dict[bytes, type[BackendMessage]] = {}
_FRONTEND_REGISTRY: dict[bytes, type[FrontendMessage]] = {}


def register(
    identifier: BackendMessageType | FrontendMessageType,
) -> Callable[[type[PGMessage]], type[PGMessage]]:
    """Class decorator that registers a message class for a given identifier byte.

    A CommonMessage (which subclasses both) is registered in *both* registries
    so it can be looked up from either side of the conversation.
    """

    def decorator(cls: type[PGMessage]) -> type[PGMessage]:
        key = identifier.encode("ascii")
        registered = False

        if issubclass(cls, BackendMessage):
            if key in _BACKEND_REGISTRY:
                raise PygwireError(
                    f"Duplicate backend registration for {identifier!r}: "
                    f"{_BACKEND_REGISTRY[key].__name__} and {cls.__name__}"
                )
            _BACKEND_REGISTRY[key] = cls
            registered = True

        if issubclass(cls, FrontendMessage):
            if key in _FRONTEND_REGISTRY:
                raise PygwireError(
                    f"Duplicate frontend registration for {identifier!r}: "
                    f"{_FRONTEND_REGISTRY[key].__name__} and {cls.__name__}"
                )
            _FRONTEND_REGISTRY[key] = cls
            registered = True

        if not registered:
            raise PygwireError(
                f"Cannot register {cls.__name__}: must subclass FrontendMessage or BackendMessage"
            )
        cls.identifier = key
        return cls

    return decorator


def lookup_backend(identifier: bytes) -> type[BackendMessage] | None:
    """Return the BackendMessage subclass registered for *identifier*, or None."""
    return _BACKEND_REGISTRY.get(identifier)


def lookup_frontend(identifier: bytes) -> type[FrontendMessage] | None:
    """Return the FrontendMessage subclass registered for *identifier*, or None."""
    return _FRONTEND_REGISTRY.get(identifier)


# ---------------------------------------------------------------------------
# Special message registry (identifier-less startup-phase messages)
# ---------------------------------------------------------------------------
# Keyed by the Int32 protocol/request code that appears at bytes 4..8.

_SPECIAL_REGISTRY: dict[int, type[SpecialMessage]] = {}


def register_special(version_code: int) -> Callable[[type[SpecialMessage]], type[SpecialMessage]]:
    """Class decorator that registers a SpecialMessage for a protocol version code."""

    def decorator(cls: type[SpecialMessage]) -> type[SpecialMessage]:
        if version_code in _SPECIAL_REGISTRY:
            raise PygwireError(
                f"Duplicate special registration for code {version_code:#x}: "
                f"{_SPECIAL_REGISTRY[version_code].__name__} and {cls.__name__}"
            )
        _SPECIAL_REGISTRY[version_code] = cls
        return cls

    return decorator


def lookup_special(version_code: int) -> type[SpecialMessage] | None:
    """Return the SpecialMessage subclass for *version_code*, or None."""
    return _SPECIAL_REGISTRY.get(version_code)


# ---------------------------------------------------------------------------
# Base message classes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PGMessage:
    """Abstract base for every PostgreSQL wire-protocol message.

    Subclasses must implement:
        encode() -> bytes
        decode(payload: memoryview) -> PGMessage  (classmethod)
    """

    identifier: ClassVar[bytes] = b""

    def encode(self) -> bytes:
        raise NotImplementedError

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        raise NotImplementedError

    def to_wire(self) -> bytes:
        """Encode this message into its full wire representation.

        Standard messages:  Byte1(identifier) + Int32(length) + payload
        Special messages (StartupMessage, SSLRequest, CancelRequest) have no
        identifier byte:   Int32(length) + payload
        The length field always includes itself (4 bytes).
        """
        payload = self.encode()
        length = 4 + len(payload)

        if not self.identifier:
            # Special message — no identifier byte.
            return struct.pack("!I", length) + payload

        buf = bytearray(1 + 4 + len(payload))
        buf[0:1] = self.identifier
        struct.pack_into("!I", buf, 1, length)
        buf[5:] = payload
        return bytes(buf)


@dataclass(slots=True)
class FrontendMessage(PGMessage):
    """Base class for messages sent by the client (Frontend)."""


@dataclass(slots=True)
class BackendMessage(PGMessage):
    """Base class for messages sent by the server (Backend)."""


@dataclass(slots=True)
class CommonMessage(FrontendMessage, BackendMessage):
    """Base class for messages used by both Frontend and Backend (e.g. CopyData)."""


@dataclass(slots=True)
class SpecialMessage(PGMessage):
    """Base class for identifier-less messages (StartupMessage, SSLRequest, CancelRequest).

    These messages have no leading identifier byte — they begin directly
    with Int32(length) + payload.  The base ``to_wire`` already handles
    this when ``identifier`` is empty (the default)."""


# ---------------------------------------------------------------------------
# Utility functions for message encoding/decoding (internal)
# ---------------------------------------------------------------------------


def _decode_field_messages(payload: memoryview) -> dict[str, str]:
    """Parse the field-based format used by ErrorResponse and NoticeResponse.

    Format: repeating (Byte1(code) + String(value)) terminated by Byte1(0).
    """
    fields: dict[str, str] = {}
    offset = 0
    while offset < len(payload):
        code = payload[offset]
        if code == 0:
            break
        offset += 1
        value, offset = _read_cstring(payload, offset)
        fields[chr(code)] = value
    return fields


def _encode_field_messages(fields: dict[str, str]) -> bytes:
    """Encode field dict into the wire format for Error/Notice responses."""
    buf = bytearray()
    for code, value in fields.items():
        buf.append(ord(code))
        buf.extend(value.encode("utf-8"))
        buf.append(0)
    buf.append(0)  # terminator
    return bytes(buf)


def _read_cstring(payload: memoryview, offset: int) -> tuple[str, int]:
    """Read a null-terminated UTF-8 string starting at *offset*.

    Returns (decoded_string, offset_past_null).
    Uses C-level byte scanning via bytes.index() for better performance.
    """
    try:
        # Convert to bytes and find null terminator using C-level scanning
        null_pos = bytes(payload[offset:]).index(0)
        end = offset + null_pos
        value = bytes(payload[offset:end]).decode("utf-8")
        return value, end + 1
    except ValueError:
        raise ProtocolError("Unterminated string in payload") from None
