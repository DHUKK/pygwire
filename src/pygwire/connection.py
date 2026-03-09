"""Sans-I/O connection classes for PostgreSQL wire protocol.

The Connection is the primary public API for pygwire. It coordinates message
decoding, encoding, and state tracking as a single unit — because you cannot
correctly decode a PostgreSQL byte stream without knowing the connection phase.

The connection classes follow the sans-I/O design pattern: they manage protocol
state and message serialization, but leave actual network I/O to the caller.

Usage (Frontend/Client)::

    from pygwire.connection import FrontendConnection
    from pygwire.messages import StartupMessage, Query
    import socket

    conn = FrontendConnection()
    sock = socket.create_connection(("localhost", 5432))

    # Send messages
    startup = StartupMessage(params={"user": "postgres", "database": "postgres"})
    sock.send(conn.send(startup))

    # Receive messages
    data = sock.recv(4096)
    for msg in conn.receive(data):
        print(f"Received: {msg}")

Usage (Backend/Server)::

    from pygwire.connection import BackendConnection
    from pygwire.messages import AuthenticationOk, ReadyForQuery

    conn = BackendConnection()

    # Receive client messages
    for msg in conn.receive(client_data):
        if isinstance(msg, StartupMessage):
            client_sock.send(conn.send(AuthenticationOk()))

Hooks for I/O Integration::

    class SocketConnection(FrontendConnection):
        def __init__(self, sock):
            super().__init__()
            self.sock = sock

        def on_send(self, data: bytes) -> None:
            self.sock.send(data)

    conn = SocketConnection(sock)
    conn.send(Query(...))  # Automatically sends to socket!

Starting at a specific phase::

    # For connection pooling or proxying where startup is already done:
    conn = FrontendConnection(initial_phase=ConnectionPhase.READY)
"""

from __future__ import annotations

import logging
from abc import ABC
from collections.abc import Iterator

from pygwire.codec import _BackendStreamDecoder, _FrontendStreamDecoder
from pygwire.constants import ConnectionPhase
from pygwire.messages import PGMessage
from pygwire.state_machine import (
    BackendStateMachine,
    FrontendStateMachine,
    StateMachineError,
)

logger = logging.getLogger(__name__)

__all__ = [
    "Connection",
    "FrontendConnection",
    "BackendConnection",
]


class Connection(ABC):
    """Base class for sans-I/O PostgreSQL connection coordination.

    Coordinates a message decoder and state machine to provide a higher-level
    API for the PostgreSQL wire protocol without performing I/O operations.

    The decoder reads the current phase from the state machine to determine
    framing mode (startup, SSL/GSS negotiation, standard) and to dispatch
    ambiguous identifiers (e.g. 'p' during SASL auth).

    This is an abstract base class — use FrontendConnection or BackendConnection.

    Args:
        initial_phase: Starting connection phase. Defaults to STARTUP.
        strict: If True (default), state machine violations raise
            StateMachineError. If False, violations are logged as warnings
            and the connection continues.
    """

    _decoder: _BackendStreamDecoder | _FrontendStreamDecoder
    _state_machine: FrontendStateMachine | BackendStateMachine
    _strict: bool

    def send(self, msg: PGMessage) -> bytes:
        """Prepare a message to send.

        Updates the state machine and encodes the message to wire format.
        Calls on_send() hook after encoding.

        Args:
            msg: Message to send

        Returns:
            Wire-format bytes to write to socket/transport

        Raises:
            StateMachineError: If message is invalid for current connection phase
                (only when strict=True)
        """
        self._send_to_state_machine(msg)
        wire_bytes = msg.to_wire()
        self.on_send(wire_bytes)
        return wire_bytes

    def receive(self, data: bytes) -> Iterator[PGMessage]:
        """Process received data and yield decoded messages.

        Feeds data to the decoder, updates state machine for each decoded
        message, and calls on_receive() hook.

        Args:
            data: Raw bytes received from socket/transport

        Yields:
            Decoded messages

        Raises:
            ProtocolError: If message framing is invalid
            StateMachineError: If message is invalid for current connection phase
                (only when strict=True)
        """
        self._decoder.feed(data)
        for msg in self._decoder:
            self._receive_to_state_machine(msg)
            self.on_receive(msg)
            yield msg

    def _send_to_state_machine(self, msg: PGMessage) -> None:
        """Update state machine for a sent message."""
        try:
            self._state_machine.send(msg)  # type: ignore[arg-type]
            # Sync decoder phase after state machine update
            self._decoder.phase = self._state_machine.phase
        except StateMachineError:
            if self._strict:
                raise
            logger.warning(
                "State machine error on send(%s) in phase %s (strict=False, continuing)",
                type(msg).__name__,
                self._state_machine.phase.name,
            )

    def _receive_to_state_machine(self, msg: PGMessage) -> None:
        """Update state machine for a received message."""
        try:
            self._state_machine.receive(msg)  # type: ignore[arg-type]
            # Sync decoder phase after state machine update
            self._decoder.phase = self._state_machine.phase
        except StateMachineError:
            if self._strict:
                raise
            logger.warning(
                "State machine error on receive(%s) in phase %s (strict=False, continuing)",
                type(msg).__name__,
                self._state_machine.phase.name,
            )

    def on_send(self, data: bytes) -> None:  # noqa: B027
        """Hook called after encoding a message for sending.

        Override this method to add I/O operations (e.g., automatically
        write to socket) or logging/metrics.

        Args:
            data: Wire-format bytes ready to be sent
        """
        pass

    def on_receive(self, msg: PGMessage) -> None:  # noqa: B027
        """Hook called after decoding and validating a received message.

        Override this method to add logging, metrics, or custom message
        handling.

        Args:
            msg: Decoded and validated message
        """
        pass

    @property
    def phase(self) -> ConnectionPhase:
        """Current connection phase."""
        return self._state_machine.phase

    @property
    def is_active(self) -> bool:
        """Check if connection is active (not terminated or failed)."""
        return self._state_machine.is_active

    @property
    def is_ready(self) -> bool:
        """Check if connection is ready to accept queries."""
        return self._state_machine.is_ready

    @property
    def pending_syncs(self) -> int:
        """Number of pending Sync responses (for pipelined extended queries)."""
        return self._state_machine.pending_syncs


class FrontendConnection(Connection):
    """Sans-I/O PostgreSQL frontend (client) connection.

    Manages client-side connection state, decoding backend messages and
    encoding frontend messages, without performing I/O operations.

    Example::

        conn = FrontendConnection()
        sock = socket.create_connection(("localhost", 5432))

        # Send startup
        sock.send(conn.send(StartupMessage(...)))

        # Receive and handle authentication
        while conn.phase != ConnectionPhase.READY:
            for msg in conn.receive(sock.recv(4096)):
                if isinstance(msg, AuthenticationMD5Password):
                    sock.send(conn.send(PasswordMessage(...)))

        # Send query
        sock.send(conn.send(Query("SELECT 1")))

        # Read results
        while conn.phase == ConnectionPhase.SIMPLE_QUERY:
            for msg in conn.receive(sock.recv(4096)):
                if isinstance(msg, DataRow):
                    print(msg.columns)
    """

    def __init__(
        self,
        *,
        initial_phase: ConnectionPhase = ConnectionPhase.STARTUP,
        strict: bool = True,
    ) -> None:
        """Initialize a frontend connection.

        Args:
            initial_phase: Starting connection phase. Defaults to STARTUP.
                Use a later phase (e.g., READY) for connection pooling or
                proxying where startup is already complete.
            strict: If True (default), state machine violations raise
                StateMachineError. If False, violations are logged as warnings.
        """
        self._strict = strict
        self._state_machine = FrontendStateMachine(phase=initial_phase)
        self._decoder = _BackendStreamDecoder()
        self._decoder.phase = initial_phase


class BackendConnection(Connection):
    """Sans-I/O PostgreSQL backend (server) connection.

    Manages server-side connection state, decoding frontend messages and
    encoding backend messages, without performing I/O operations.

    Example::

        conn = BackendConnection()

        # Receive startup message
        for msg in conn.receive(client_data):
            if isinstance(msg, StartupMessage):
                client_sock.send(conn.send(AuthenticationOk()))
                client_sock.send(conn.send(ReadyForQuery(...)))

        # Receive and respond to queries
        for msg in conn.receive(client_data):
            if isinstance(msg, Query):
                client_sock.send(conn.send(RowDescription(...)))
                client_sock.send(conn.send(DataRow(...)))
                client_sock.send(conn.send(CommandComplete(...)))
                client_sock.send(conn.send(ReadyForQuery(...)))
    """

    def __init__(
        self,
        *,
        initial_phase: ConnectionPhase = ConnectionPhase.STARTUP,
        strict: bool = True,
    ) -> None:
        """Initialize a backend connection.

        Args:
            initial_phase: Starting connection phase. Defaults to STARTUP.
                Use a later phase (e.g., READY) for connection pooling or
                proxying where startup is already complete.
            strict: If True (default), state machine violations raise
                StateMachineError. If False, violations are logged as warnings.
        """
        self._strict = strict
        self._state_machine = BackendStateMachine(phase=initial_phase)
        self._decoder = _FrontendStreamDecoder()
        self._decoder.phase = initial_phase
