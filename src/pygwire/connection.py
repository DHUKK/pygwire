"""Sans-I/O connection coordination for PostgreSQL wire protocol.

This module provides high-level connection classes that coordinate message
decoding/encoding with state machine tracking, without performing I/O operations.

The connection classes follow the sans-I/O design pattern - they manage protocol
state and message serialization, but leave actual network I/O to the user.

Usage (Frontend/Client)::

    from pygwire.connection import FrontendConnection
    from pygwire.messages import StartupMessage, Query
    import socket

    # Create connection and socket
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
            # Send response
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
"""

from __future__ import annotations

from abc import ABC
from collections.abc import Iterator

from pygwire.codec import BackendMessageDecoder, FrontendMessageDecoder
from pygwire.messages import BackendMessage, FrontendMessage, PGMessage
from pygwire.state_machine import (
    BackendStateMachine,
    ConnectionPhase,
    FrontendStateMachine,
)

__all__ = [
    "Connection",
    "FrontendConnection",
    "BackendConnection",
]


class Connection(ABC):
    """Base class for sans-I/O PostgreSQL connection coordination.

    Coordinates a message decoder and state machine to provide a higher-level
    API for the PostgreSQL wire protocol without performing I/O operations.

    This is an abstract base class - use FrontendConnection or BackendConnection.

    Attributes:
        decoder: Message decoder for incoming data
        state_machine: State machine for protocol validation
    """

    decoder: BackendMessageDecoder | FrontendMessageDecoder
    state_machine: FrontendStateMachine | BackendStateMachine

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
        """
        self.state_machine.send(msg)  # type: ignore[arg-type]
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
        """
        self.decoder.feed(data)
        for msg in self.decoder:
            # Only track backend/frontend messages in state machine
            # (SpecialMessage like SSLRequest are not tracked)
            if isinstance(msg, (BackendMessage, FrontendMessage)):
                self.state_machine.receive(msg)  # type: ignore[arg-type]
                self.on_receive(msg)
            yield msg

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
        """Current connection phase.

        Returns:
            Current phase of the connection state machine
        """
        return self.state_machine.phase

    @property
    def is_active(self) -> bool:
        """Check if connection is active (not terminated or failed).

        Returns:
            True if connection is active, False if terminated/failed
        """
        return self.state_machine.is_active


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

    def __init__(self) -> None:
        """Initialize a frontend connection.

        Sets up a BackendMessageDecoder (to decode server responses) and
        a FrontendStateMachine (to track client-side protocol state).
        """
        self.decoder = BackendMessageDecoder()
        self.state_machine = FrontendStateMachine()


class BackendConnection(Connection):
    """Sans-I/O PostgreSQL backend (server) connection.

    Manages server-side connection state, decoding frontend messages and
    encoding backend messages, without performing I/O operations.

    Example::

        conn = BackendConnection()

        # Receive startup message
        for msg in conn.receive(client_data):
            if isinstance(msg, StartupMessage):
                # Send authentication
                client_sock.send(conn.send(AuthenticationOk()))
                client_sock.send(conn.send(ReadyForQuery(...)))

        # Receive and respond to queries
        for msg in conn.receive(client_data):
            if isinstance(msg, Query):
                # Send results
                client_sock.send(conn.send(RowDescription(...)))
                client_sock.send(conn.send(DataRow(...)))
                client_sock.send(conn.send(CommandComplete(...)))
                client_sock.send(conn.send(ReadyForQuery(...)))
    """

    def __init__(self, *, startup: bool = True) -> None:
        """Initialize a backend connection.

        Sets up a FrontendMessageDecoder (to decode client requests) and
        a BackendStateMachine (to track server-side protocol state).

        Args:
            startup: Whether to expect startup messages (default True).
                Set to False if the connection has already completed startup
                (e.g., for connection pooling or protocol proxying).
        """
        self.decoder = FrontendMessageDecoder(startup=startup)
        self.state_machine = BackendStateMachine()
