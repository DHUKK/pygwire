"""Sans-I/O StreamDecoder for the PostgreSQL wire protocol.

The decoders in this module are internal implementation details of the
Connection classes. They use the framing strategy system to extract messages
based on the current connection phase.
"""

from __future__ import annotations

from collections import deque
from typing import Self

from pygwire.constants import ConnectionPhase, MessageDirection
from pygwire.framing import lookup_framing
from pygwire.messages import PGMessage

# Compact the buffer once this many bytes have been consumed from the front.
_COMPACTION_THRESHOLD = 4096


class _BaseStreamDecoder:
    """Base class for stream decoders. Internal use only.

    The decoder maintains its own phase that is synchronized by the Connection.
    It uses framing strategies to extract messages based on the current phase
    and direction.
    """

    __slots__ = (
        "_buf",
        "_pos",
        "_messages",
        "_direction",
        "_phase",
    )

    def __init__(self, direction: MessageDirection) -> None:
        """Initialize decoder.

        Args:
            direction: Message direction (who sends these messages)
        """
        self._buf = bytearray()
        self._pos: int = 0
        self._messages: deque[PGMessage] = deque()
        self._direction = direction
        self._phase = ConnectionPhase.STARTUP

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def phase(self) -> ConnectionPhase:
        """Current connection phase."""
        return self._phase

    @phase.setter
    def phase(self, value: ConnectionPhase) -> None:
        """Set connection phase.

        The Connection updates this after each state machine transition.
        """
        self._phase = value

    @property
    def buffered(self) -> int:
        """Number of unprocessed bytes remaining in the internal buffer."""
        return len(self._buf) - self._pos

    def feed(self, data: bytes | bytearray | memoryview) -> None:
        """Append data to the internal buffer.

        This may be called with arbitrarily sized chunks — partial messages
        are buffered until enough data arrives. Messages are parsed lazily
        when requested through the iterator protocol, allowing the phase to
        be updated between each message.

        Args:
            data: Raw bytes to add to the buffer
        """
        if not data:
            return

        self._buf.extend(data)

    def read(self) -> PGMessage | None:
        """Return the next decoded message, or None if none are ready."""
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
        # Try to get a message from the queue
        msg = self.read()
        if msg is not None:
            return msg

        # Queue is empty, try to parse one more message from buffer
        self._parse()
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

    def _compact(self) -> None:
        """Remove already-consumed bytes from the front of the buffer.

        Called periodically to prevent the buffer from growing without bound
        when many small messages arrive.
        """
        if self._pos > 0:
            del self._buf[: self._pos]
            self._pos = 0

    def _parse(self) -> None:
        """Parse one complete message from the buffer if available.

        Only parses a single message per call to allow the phase to be updated
        between messages when they arrive in batches. The caller (Connection.receive)
        will call this repeatedly through the iterator protocol.

        Uses framing strategies to extract messages based on the current
        phase and direction. The framing strategy handles all the details
        of message extraction and decoding.

        Uses memoryview for zero-copy payload slicing.
        """
        # Get framing strategy for current phase
        framing = lookup_framing(self._phase, self._direction)

        # Let framing strategy try to parse a message
        result = framing.try_parse(
            buf=memoryview(self._buf),
            pos=self._pos,
            phase=self._phase,
            direction=self._direction,
        )

        if result is None:
            # Not enough data for a complete message
            return

        msg, consumed = result
        self._pos += consumed
        self._messages.append(msg)

        # Check if we should compact the buffer
        if self._pos > _COMPACTION_THRESHOLD:
            self._compact()


class _FrontendStreamDecoder(_BaseStreamDecoder):
    """Decoder for messages sent BY frontend (client).

    Used by BackendConnection (server) to decode incoming client messages.

    Examples:
        - Query (client sends to server)
        - StartupMessage (client initiates connection)
        - PasswordMessage (client responds to auth challenge)
    """

    def __init__(self) -> None:
        super().__init__(direction=MessageDirection.FRONTEND)


class _BackendStreamDecoder(_BaseStreamDecoder):
    """Decoder for messages sent BY backend (server).

    Used by FrontendConnection (client) to decode incoming server messages.

    Examples:
        - RowDescription (server sends to client)
        - ReadyForQuery (server signals ready state)
        - AuthenticationOk (server accepts authentication)
    """

    def __init__(self) -> None:
        super().__init__(direction=MessageDirection.BACKEND)
