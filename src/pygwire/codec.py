"""Sans-I/O StreamDecoder for the PostgreSQL wire protocol.

The decoders provide incremental message parsing with phase-aware framing.
They are stateful but designed to be manageable - users must synchronize
the phase property when connection state changes.

Use the decoder classes directly when you need fine-grained control over
message parsing without the full Connection state machine. For most use cases,
prefer the higher-level Connection classes which coordinate decoder + state
machine automatically.
"""

from __future__ import annotations

from collections import deque
from typing import Self

from pygwire.constants import ConnectionPhase, MessageDirection
from pygwire.framing import lookup_framing
from pygwire.messages import PGMessage

# Compact the buffer once this many bytes have been consumed from the front.
_COMPACTION_THRESHOLD = 4096

__all__ = [
    "BackendMessageDecoder",
    "FrontendMessageDecoder",
]


class StreamDecoder:
    """Base class for phase-aware stream decoders.

    The decoder maintains a connection phase that determines message framing.
    When used standalone (without Connection), the user is responsible for
    updating the phase property to match connection state transitions.

    This class handles:
    - Incremental parsing of wire protocol bytes
    - Phase-dependent message framing (startup vs standard)
    - Zero-copy buffer management using memoryview
    - Message queueing for batch arrivals

    Note:
        For most use cases, prefer FrontendConnection or BackendConnection
        which automatically coordinate decoder phase with state machine.
        Use this class directly only when you need custom state management.
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

        When using the decoder standalone (without Connection), update this
        after each connection state transition to ensure correct message framing.
        The Connection class handles this automatically.
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


class FrontendMessageDecoder(StreamDecoder):
    """Decoder for messages sent BY frontend (client).

    Used by servers (BackendConnection) to decode incoming client messages,
    or standalone when building custom PostgreSQL server implementations.

    Examples of decoded messages:
        - StartupMessage: Client initiates connection
        - Query: Client sends simple query
        - PasswordMessage: Client responds to auth challenge
        - Parse/Bind/Execute: Client uses extended query protocol

    Usage::

        decoder = FrontendMessageDecoder()
        decoder.phase = ConnectionPhase.STARTUP

        # Feed data from client socket
        decoder.feed(client_data)

        # Process messages
        for msg in decoder:
            if isinstance(msg, StartupMessage):
                # Handle startup...
                decoder.phase = ConnectionPhase.AUTHENTICATION
            elif isinstance(msg, Query):
                # Handle query...
    """

    def __init__(self) -> None:
        super().__init__(direction=MessageDirection.FRONTEND)


class BackendMessageDecoder(StreamDecoder):
    """Decoder for messages sent BY backend (server).

    Used by clients (FrontendConnection) to decode incoming server messages,
    or standalone when building custom PostgreSQL client implementations.

    Examples of decoded messages:
        - AuthenticationOk: Server accepts authentication
        - RowDescription: Server describes result columns
        - DataRow: Server sends result row
        - ReadyForQuery: Server signals ready for next query
        - ErrorResponse: Server reports an error

    Usage::

        decoder = BackendMessageDecoder()
        decoder.phase = ConnectionPhase.STARTUP

        # Feed data from server socket
        decoder.feed(server_data)

        # Process messages
        for msg in decoder:
            if isinstance(msg, AuthenticationOk):
                # Authentication succeeded...
                decoder.phase = ConnectionPhase.READY
            elif isinstance(msg, DataRow):
                # Process result row...
    """

    def __init__(self) -> None:
        super().__init__(direction=MessageDirection.BACKEND)
