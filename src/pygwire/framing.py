"""Framing strategies for PostgreSQL wire protocol message extraction.

This module defines how to extract different types of PostgreSQL messages
from a byte buffer. PostgreSQL uses three distinct framing modes:

1. **Startup framing**: Int32(length) + payload (no identifier byte)
   - Used during STARTUP phase for StartupMessage, SSLRequest, etc.
   - First 4 bytes of payload contain version/request code

2. **Negotiation framing**: Single byte (no length, no identifier)
   - Used for SSL/GSS negotiation responses (b'S', b'N', b'G')
   - The byte itself IS the complete message

3. **Standard framing**: Byte1(identifier) + Int32(length) + payload
   - Used for all other messages after authentication begins
   - Most common framing mode
"""

from __future__ import annotations

import struct
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pygwire.constants import ConnectionPhase, MessageDirection
from pygwire.exceptions import FramingError
from pygwire.messages import (
    NEGOTIATION_REGISTRY,
    STANDARD_REGISTRY,
    STARTUP_REGISTRY,
)

if TYPE_CHECKING:
    from pygwire.messages import PGMessage

__all__ = [
    "FramingStrategy",
    "NegotiationFraming",
    "StandardFraming",
    "StartupFraming",
    "lookup_framing",
]

_LENGTH_STRUCT = struct.Struct("!I")
_DEFAULT_MAX_MESSAGE_SIZE = 1 * 1024 * 1024 * 1024


class FramingStrategy(ABC):
    """Abstract base class for message framing strategies.

    A framing strategy knows how to extract a single message from a byte buffer
    based on the PostgreSQL wire protocol framing rules. Different phases of
    the protocol use different framing modes.
    """

    def __init__(self, max_message_size: int = _DEFAULT_MAX_MESSAGE_SIZE):
        """Initialize framing strategy.

        Args:
            max_message_size: Maximum allowed message size in bytes.
                Defaults to 1 GB (PostgreSQL's PQ_LARGE_MESSAGE_LIMIT).
        """
        self._max_message_size = max_message_size

    @abstractmethod
    def try_parse(
        self,
        buf: memoryview,
        pos: int,
        phase: ConnectionPhase,
        direction: MessageDirection,
    ) -> tuple[PGMessage, int] | None:
        """Try to extract one message from the buffer.

        Args:
            buf: Buffer containing message bytes (memoryview for zero-copy)
            pos: Current position in buffer
            phase: Current connection phase
            direction: Message direction (FRONTEND or BACKEND)

        Returns:
            (message, bytes_consumed) if successful, None if insufficient data

        Raises:
            FramingError: If message is malformed or unknown
        """
        ...


class StartupFraming(FramingStrategy):
    """Framing for startup messages: Int32(length) + payload.

    Startup messages have no identifier byte. The frame starts with a 4-byte
    length (including the length field itself), followed by payload. The first
    4 bytes of the payload contain a version/request code that identifies the
    message type.

    Wire format:
        Bytes 0-3:   Int32 length (including these 4 bytes)
        Bytes 4-7:   Int32 request_code (part of payload)
        Bytes 8+:    Remaining payload

    Example:
        StartupMessage: length=52, request_code=0x00030000, params...
        SSLRequest:     length=8,  request_code=80877103
    """

    def try_parse(
        self,
        buf: memoryview,
        pos: int,
        phase: ConnectionPhase,
        direction: MessageDirection,
    ) -> tuple[PGMessage, int] | None:
        if len(buf) - pos < 4:
            return None

        (length,) = _LENGTH_STRUCT.unpack_from(buf, pos)
        if length > self._max_message_size:
            raise FramingError(
                f"Startup message length {length} exceeds maximum allowed size "
                f"({self._max_message_size})"
            )

        if len(buf) - pos < length:
            return None

        payload_start = pos + 4
        payload_end = pos + length
        payload = buf[payload_start:payload_end]
        if len(payload) < 4:
            raise FramingError("Startup message payload too short for request code")

        (request_code,) = _LENGTH_STRUCT.unpack_from(payload)

        msg_cls = STARTUP_REGISTRY.lookup(request_code)
        if msg_cls is None:
            raise FramingError(f"Unknown startup message request code: {request_code:#010x}")
        try:
            msg = msg_cls.decode(payload)
        except struct.error as e:
            raise FramingError(f"{msg_cls.__name__} message truncated or malformed: {e}") from e

        return msg, length


class NegotiationFraming(FramingStrategy):
    """Framing for SSL/GSS negotiation: Single byte.

    Negotiation messages are exactly 1 byte with no length field. The byte
    value itself identifies the message and its meaning:
        - b'S': SSL accepted
        - b'N': SSL/GSS rejected
        - b'G': GSS accepted

    These are the only messages in the protocol without any length framing.
    """

    def try_parse(
        self,
        buf: memoryview,
        pos: int,
        phase: ConnectionPhase,
        direction: MessageDirection,
    ) -> tuple[PGMessage, int] | None:
        if len(buf) - pos < 1:
            return None

        byte_value = bytes(buf[pos : pos + 1])

        msg_cls = NEGOTIATION_REGISTRY.lookup(byte_value, phase)
        if msg_cls is None:
            raise FramingError(f"Unknown negotiation byte: {byte_value!r} in phase {phase.name}")

        payload = buf[pos : pos + 1]
        try:
            msg = msg_cls.decode(payload)
        except struct.error as e:
            raise FramingError(f"{msg_cls.__name__} message malformed: {e}") from e

        return msg, 1


class StandardFraming(FramingStrategy):
    """Framing for standard messages: Byte1(identifier) + Int32(length) + payload.

    This is the most common framing mode, used for all messages after the
    initial handshake. Messages start with a 1-byte identifier, followed by
    a 4-byte length (which includes the length field itself but NOT the
    identifier byte), followed by payload.

    Wire format:
        Byte 0:      Identifier (e.g., 'Q' for Query, 'Z' for ReadyForQuery)
        Bytes 1-4:   Int32 length (includes these 4 bytes, NOT identifier)
        Bytes 5+:    Payload

    Example:
        Query('SELECT 1'): identifier=b'Q', length=14, payload="SELECT 1\x00"
        ReadyForQuery(I):  identifier=b'Z', length=5,  payload=b'I'
    """

    def try_parse(
        self,
        buf: memoryview,
        pos: int,
        phase: ConnectionPhase,
        direction: MessageDirection,
    ) -> tuple[PGMessage, int] | None:
        if len(buf) - pos < 5:
            return None

        identifier = bytes((buf[pos],))
        (length,) = _LENGTH_STRUCT.unpack_from(buf, pos + 1)
        if length > self._max_message_size:
            raise FramingError(
                f"Message length {length} exceeds maximum allowed size ({self._max_message_size})"
            )

        total = 1 + length
        if len(buf) - pos < total:
            return None

        payload_start = pos + 5
        payload_end = pos + total
        payload = buf[payload_start:payload_end]

        msg_cls = STANDARD_REGISTRY.lookup(identifier, phase, direction)
        if msg_cls is None:
            raise FramingError(
                f"Unknown message identifier: {identifier!r} in phase {phase.name} "
                f"for direction {direction.value}"
            )
        try:
            msg = msg_cls.decode(payload)
        except struct.error as e:
            raise FramingError(f"{msg_cls.__name__} message truncated or malformed: {e}") from e

        return msg, total


_STANDARD = StandardFraming()
_STARTUP = StartupFraming()
_NEGOTIATION = NegotiationFraming()

_FRAMING_REGISTRY: dict[tuple[ConnectionPhase, MessageDirection], FramingStrategy] = {
    (ConnectionPhase.STARTUP, MessageDirection.FRONTEND): _STARTUP,
    (ConnectionPhase.SSL_NEGOTIATION, MessageDirection.BACKEND): _NEGOTIATION,
    (ConnectionPhase.GSS_NEGOTIATION, MessageDirection.BACKEND): _NEGOTIATION,
}


def lookup_framing(phase: ConnectionPhase, direction: MessageDirection) -> FramingStrategy:
    """Find the framing strategy for a given phase and direction.

    Returns the registered strategy, or standard framing as the default.
    """
    return _FRAMING_REGISTRY.get((phase, direction), _STANDARD)
