"""Sans-I/O StreamDecoder for the PostgreSQL wire protocol."""

from __future__ import annotations

import struct
from collections import deque
from collections.abc import Callable
from typing import Self

from pygwire.messages import (
    BackendMessage,
    FrontendMessage,
    PGMessage,
    ProtocolError,
    StartupMessage,
    lookup_backend,
    lookup_frontend,
    lookup_special,
)

# Minimum standard message size: 1 byte identifier + 4 bytes length.
_HEADER_SIZE = 5
# Special (startup) messages have no identifier: just 4 bytes length.
_SPECIAL_HEADER_SIZE = 4
# Struct format for the 4-byte length field (network byte order).
_LENGTH_STRUCT = struct.Struct("!I")
# Compact the buffer once this many bytes have been consumed from the front.
_COMPACTION_THRESHOLD = 4096
# Default maximum message size (1 GB, matching PostgreSQL's PQ_LARGE_MESSAGE_LIMIT).
_DEFAULT_MAX_MESSAGE_SIZE = 1 * 1024 * 1024 * 1024


class _BaseStreamDecoder:
    """Base class for stream decoders. Internal use only."""

    __slots__ = ("_buf", "_pos", "_messages", "_lookup_fn", "_in_startup", "_max_message_size")

    def __init__(
        self,
        lookup_fn: Callable[[bytes], type[BackendMessage] | type[FrontendMessage] | None],
        *,
        startup: bool = False,
        max_message_size: int = _DEFAULT_MAX_MESSAGE_SIZE,
    ) -> None:
        self._buf = bytearray()
        self._pos: int = 0
        self._messages: deque[PGMessage] = deque()
        self._lookup_fn = lookup_fn
        self._in_startup = startup
        self._max_message_size = max_message_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def in_startup(self) -> bool:
        """True while the decoder expects an identifier-less startup packet."""
        return self._in_startup

    @property
    def buffered(self) -> int:
        """Number of unprocessed bytes remaining in the internal buffer."""
        return len(self._buf) - self._pos

    def feed(self, data: bytes | bytearray | memoryview) -> None:
        """Append *data* to the internal buffer and parse all complete messages.

        This may be called with arbitrarily sized chunks — partial messages
        are buffered until enough data arrives.
        """
        if not data:
            return

        self._buf.extend(data)
        self._parse()

    def read(self) -> PGMessage | None:
        """Return the next decoded message, or ``None`` if none are ready."""
        if self._messages:
            return self._messages.popleft()
        return None

    def read_all(self) -> list[PGMessage]:
        """Drain and return all currently decoded messages."""
        msgs = list(self._messages)
        self._messages.clear()
        return msgs

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> PGMessage:
        msg = self.read()
        if msg is None:
            raise StopIteration
        return msg

    def clear(self) -> None:
        """Discard all buffered data and pending messages."""
        self._buf.clear()
        self._pos = 0
        self._messages.clear()

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    def _lookup(self, identifier: int) -> type[PGMessage]:
        """Resolve a single-byte identifier to a message class."""
        key = bytes((identifier,))
        cls = self._lookup_fn(key)
        if cls is None:
            raise ProtocolError(f"Unknown message identifier: {key!r}")
        return cls

    def _compact(self) -> None:
        """Remove already-consumed bytes from the front of the buffer.

        Called periodically to prevent the buffer from growing without bound
        when many small messages arrive.
        """
        if self._pos > 0:
            del self._buf[: self._pos]
            self._pos = 0

    def _parse(self) -> None:
        """Parse as many complete messages as possible from the buffer.

        Handles two framing modes:
        - **Startup phase** (``_in_startup``): messages have no identifier
          byte — framing is ``Int32(length) + payload``.  The first 4 bytes
          of the payload contain the protocol version / request code used to
          dispatch via the special-message registry.
        - **Standard phase**: messages are ``Byte1(id) + Int32(length) + payload``.

        Uses :class:`memoryview` for zero-copy payload slicing.  Views are
        created and released per-message so the buffer can be compacted.
        """
        needs_compact = False

        while True:
            remaining = len(self._buf) - self._pos

            if self._in_startup:
                msg = self._try_parse_startup(remaining)
                if msg is None:
                    break
                self._messages.append(msg)
                # Exit startup mode only after receiving StartupMessage
                if isinstance(msg, StartupMessage):
                    self._in_startup = False
            else:
                msg = self._try_parse_standard(remaining)
                if msg is None:
                    break
                self._messages.append(msg)

            if self._pos > _COMPACTION_THRESHOLD:
                needs_compact = True

        if needs_compact:
            self._compact()

    def _try_parse_startup(self, remaining: int) -> PGMessage | None:
        """Attempt to parse a single identifier-less startup message.

        Returns the decoded message or None if insufficient data.
        """
        if remaining < _SPECIAL_HEADER_SIZE:
            return None

        (length,) = _LENGTH_STRUCT.unpack_from(self._buf, self._pos)
        if length > self._max_message_size:
            raise ProtocolError(
                f"Startup message length {length} exceeds maximum allowed size "
                f"({self._max_message_size})"
            )
        if remaining < length:
            return None

        # Payload starts right after the 4-byte length.
        payload_start = self._pos + _SPECIAL_HEADER_SIZE
        payload_end = self._pos + length

        view = memoryview(self._buf)
        payload = view[payload_start:payload_end]

        # First 4 bytes of the payload are the protocol version / request code.
        if len(payload) < 4:
            del payload, view
            raise ProtocolError("Startup message payload too short for version code")

        (version_code,) = _LENGTH_STRUCT.unpack_from(payload)

        msg_cls = lookup_special(version_code)
        if msg_cls is None:
            del payload, view
            raise ProtocolError(f"Unknown startup message version code: {version_code:#010x}")

        try:
            msg = msg_cls.decode(payload)
        except struct.error as e:
            raise ProtocolError(f"{msg_cls.__name__} message truncated or malformed: {e}") from e
        finally:
            del payload, view

        self._pos = payload_end
        return msg

    def _try_parse_standard(self, remaining: int) -> PGMessage | None:
        """Attempt to parse a single standard (identifier + length) message.

        Returns the decoded message or None if insufficient data.
        """
        if remaining < _HEADER_SIZE:
            return None

        # Read identifier as an integer — avoids creating a bytes object.
        ident_byte = self._buf[self._pos]
        (length,) = _LENGTH_STRUCT.unpack_from(self._buf, self._pos + 1)
        if length > self._max_message_size:
            raise ProtocolError(
                f"Message length {length} exceeds maximum allowed size ({self._max_message_size})"
            )

        total = 1 + length  # identifier byte + length-includes-self + payload
        if remaining < total:
            return None

        payload_start = self._pos + _HEADER_SIZE
        payload_end = self._pos + total

        view = memoryview(self._buf)
        payload = view[payload_start:payload_end]

        msg_cls = self._lookup(ident_byte)
        try:
            msg = msg_cls.decode(payload)
        except struct.error as e:
            raise ProtocolError(f"{msg_cls.__name__} message truncated or malformed: {e}") from e
        finally:
            del payload, view

        self._pos = payload_end
        return msg


class FrontendMessageDecoder(_BaseStreamDecoder):
    """Decoder for frontend messages (sent by clients).

    Use this decoder to parse frontend messages - that is, messages sent by PostgreSQL
    clients (psql, application code, etc.) to the server.

    Usage::

        # In a PostgreSQL server or proxy:
        decoder = FrontendMessageDecoder(startup=True)
        decoder.feed(data_from_client)
        for msg in decoder:
            if isinstance(msg, Query):
                # Client sent a query
                pass
    """

    def __init__(
        self,
        *,
        startup: bool = False,
        max_message_size: int = _DEFAULT_MAX_MESSAGE_SIZE,
    ) -> None:
        """Initialize a frontend message decoder.

        Args:
            startup: If True, expect identifier-less startup messages first.
            max_message_size: Maximum allowed message size in bytes.
                Raises ``ProtocolError`` if a message declares a length
                exceeding this value.  Defaults to 1 GB.
        """
        super().__init__(lookup_frontend, startup=startup, max_message_size=max_message_size)


class BackendMessageDecoder(_BaseStreamDecoder):
    """Decoder for backend messages (sent by servers).

    Use this decoder to parse backend messages - that is, messages sent by PostgreSQL
    servers back to clients in response to queries and other operations.

    Note:
        Backend messages never use startup mode. PostgreSQL servers only send
        standard messages with identifier bytes, never identifier-less startup
        messages (those are only sent by clients).

    Usage::

        # In a PostgreSQL client or proxy:
        decoder = BackendMessageDecoder()
        decoder.feed(data_from_server)
        for msg in decoder:
            if isinstance(msg, ReadyForQuery):
                # Server is ready for next command
                pass
    """

    def __init__(self, *, max_message_size: int = _DEFAULT_MAX_MESSAGE_SIZE) -> None:
        """Initialize a backend message decoder.

        Backend messages always use standard framing (Byte1 + Int32 + payload).

        Args:
            max_message_size: Maximum allowed message size in bytes.
                Raises ``ProtocolError`` if a message declares a length
                exceeding this value.  Defaults to 1 GB.
        """
        super().__init__(lookup_backend, startup=False, max_message_size=max_message_size)
