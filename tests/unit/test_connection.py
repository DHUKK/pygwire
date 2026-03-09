"""Tests for connection coordination classes."""

from pygwire.connection import BackendConnection, FrontendConnection
from pygwire.constants import TransactionStatus
from pygwire.messages import (
    AuthenticationOk,
    CommandComplete,
    DataRow,
    FieldDescription,
    Query,
    ReadyForQuery,
    RowDescription,
    StartupMessage,
    Terminate,
)
from pygwire.state_machine import ConnectionPhase


class TestFrontendConnection:
    """Tests for FrontendConnection class."""

    def test_initialization(self):
        """Test that FrontendConnection initializes correctly."""
        conn = FrontendConnection()
        assert conn.phase == ConnectionPhase.STARTUP
        assert conn.is_active

    def test_send_encodes_and_tracks_state(self):
        """Test that send() encodes message and updates state machine."""
        conn = FrontendConnection()
        startup = StartupMessage(params={"user": "test", "database": "test"})

        wire_bytes = conn.send(startup)

        assert isinstance(wire_bytes, bytes)
        assert len(wire_bytes) > 0
        # Sending startup doesn't change phase yet (we stay in STARTUP until we receive auth response)
        assert conn.phase == ConnectionPhase.STARTUP

    def test_receive_decodes_and_tracks_state(self):
        """Test that receive() decodes messages and updates state machine."""
        conn = FrontendConnection()
        conn.send(StartupMessage(params={"user": "test", "database": "test"}))

        # Encode backend messages
        auth_ok = AuthenticationOk()
        ready = ReadyForQuery(status=TransactionStatus.IDLE)
        data = auth_ok.to_wire() + ready.to_wire()

        # Receive and decode
        messages = list(conn.receive(data))

        assert len(messages) == 2
        assert isinstance(messages[0], AuthenticationOk)
        assert isinstance(messages[1], ReadyForQuery)
        assert conn.phase == ConnectionPhase.READY

    def test_hooks_are_called(self):
        """Test that on_send and on_receive hooks are called."""
        sent_data = []
        received_msgs = []

        class TestConnection(FrontendConnection):
            def on_send(self, data: bytes) -> None:
                sent_data.append(data)

            def on_receive(self, msg) -> None:
                received_msgs.append(msg)

        conn = TestConnection()
        startup = StartupMessage(params={"user": "test", "database": "test"})
        conn.send(startup)

        auth_ok = AuthenticationOk()
        list(conn.receive(auth_ok.to_wire()))

        assert len(sent_data) == 1
        assert len(received_msgs) == 1
        assert isinstance(received_msgs[0], AuthenticationOk)

    def test_phase_property(self):
        """Test that phase property returns current phase."""
        conn = FrontendConnection()
        assert conn.phase == ConnectionPhase.STARTUP

        # Send startup and receive authentication response
        conn.send(StartupMessage(params={"user": "test", "database": "test"}))
        list(conn.receive(AuthenticationOk().to_wire()))
        # After receiving AuthenticationOk, we're in INITIALIZATION phase
        assert conn.phase == ConnectionPhase.INITIALIZATION

    def test_is_active_property(self):
        """Test that is_active property reflects state machine state."""
        conn = FrontendConnection()
        assert conn.is_active

        # Authenticate and reach READY
        conn.send(StartupMessage(params={"user": "test", "database": "test"}))
        list(conn.receive(AuthenticationOk().to_wire()))
        list(conn.receive(ReadyForQuery(status=TransactionStatus.IDLE).to_wire()))
        assert conn.is_active

        # Terminate
        conn.send(Terminate())
        assert conn.phase == ConnectionPhase.TERMINATING


class TestBackendConnection:
    """Tests for BackendConnection class."""

    def test_initialization(self):
        """Test that BackendConnection initializes correctly."""
        conn = BackendConnection()
        assert conn.phase == ConnectionPhase.STARTUP
        assert conn.is_active

    def test_initialization_at_ready_phase(self):
        """Test that BackendConnection can start at READY phase."""
        conn = BackendConnection(initial_phase=ConnectionPhase.READY)
        assert conn.phase == ConnectionPhase.READY

    def test_send_encodes_and_tracks_state(self):
        """Test that send() encodes message and updates state machine."""
        conn = BackendConnection()

        # Receive startup first
        startup = StartupMessage(params={"user": "test", "database": "test"})
        list(conn.receive(startup.to_wire()))

        # Send authentication
        wire_bytes = conn.send(AuthenticationOk())

        assert isinstance(wire_bytes, bytes)
        assert len(wire_bytes) > 0

    def test_receive_decodes_and_tracks_state(self):
        """Test that receive() decodes messages and updates state machine."""
        conn = BackendConnection()

        # Receive startup message
        startup = StartupMessage(params={"user": "test", "database": "test"})
        messages = list(conn.receive(startup.to_wire()))

        assert len(messages) == 1
        assert isinstance(messages[0], StartupMessage)
        # Receiving startup moves us to AUTHENTICATING
        assert conn.phase == ConnectionPhase.STARTUP

    def test_query_flow(self):
        """Test full query flow from client to server."""
        conn = BackendConnection()

        # Complete startup
        startup = StartupMessage(params={"user": "test", "database": "test"})
        list(conn.receive(startup.to_wire()))
        conn.send(AuthenticationOk())
        conn.send(ReadyForQuery(status=TransactionStatus.IDLE))

        # Receive query
        query = Query(query_string="SELECT 1")
        messages = list(conn.receive(query.to_wire()))
        assert len(messages) == 1
        assert isinstance(messages[0], Query)
        assert conn.phase == ConnectionPhase.SIMPLE_QUERY

        # Send results
        conn.send(
            RowDescription(
                fields=[
                    FieldDescription(
                        name="?column?",
                        table_oid=0,
                        column_attr=0,
                        type_oid=23,
                        type_size=4,
                        type_modifier=-1,
                        format_code=0,
                    )
                ]
            )
        )
        conn.send(DataRow(columns=[b"1"]))
        conn.send(CommandComplete(tag="SELECT 1"))
        conn.send(ReadyForQuery(status=TransactionStatus.IDLE))

        assert conn.phase == ConnectionPhase.READY


class TestConnectionIntegration:
    """Integration tests for frontend and backend connections."""

    def test_client_server_handshake(self):
        """Test full client-server handshake."""
        client = FrontendConnection()
        server = BackendConnection()

        # Client sends startup
        startup = StartupMessage(params={"user": "test", "database": "test"})
        startup_bytes = client.send(startup)

        # Server receives startup
        messages = list(server.receive(startup_bytes))
        assert len(messages) == 1
        assert isinstance(messages[0], StartupMessage)

        # Server sends authentication
        auth_bytes = server.send(AuthenticationOk())
        ready_bytes = server.send(ReadyForQuery(status=TransactionStatus.IDLE))

        # Client receives authentication
        messages = list(client.receive(auth_bytes + ready_bytes))
        assert len(messages) == 2
        assert client.phase == ConnectionPhase.READY
        assert server.phase == ConnectionPhase.READY

    def test_query_response_cycle(self):
        """Test full query-response cycle."""
        client = FrontendConnection()
        server = BackendConnection()

        # Complete handshake
        startup_bytes = client.send(StartupMessage(params={"user": "test", "database": "test"}))
        list(server.receive(startup_bytes))
        auth_bytes = server.send(AuthenticationOk()) + server.send(
            ReadyForQuery(status=TransactionStatus.IDLE)
        )
        list(client.receive(auth_bytes))

        # Client sends query
        query_bytes = client.send(Query(query_string="SELECT 1"))

        # Server receives query
        messages = list(server.receive(query_bytes))
        assert len(messages) == 1
        assert isinstance(messages[0], Query)
        assert server.phase == ConnectionPhase.SIMPLE_QUERY

        # Server sends results
        result_bytes = b""
        result_bytes += server.send(
            RowDescription(
                fields=[
                    FieldDescription(
                        name="?column?",
                        table_oid=0,
                        column_attr=0,
                        type_oid=23,
                        type_size=4,
                        type_modifier=-1,
                        format_code=0,
                    )
                ]
            )
        )
        result_bytes += server.send(DataRow(columns=[b"1"]))
        result_bytes += server.send(CommandComplete(tag="SELECT 1"))
        result_bytes += server.send(ReadyForQuery(status=TransactionStatus.IDLE))

        # Client receives results
        messages = list(client.receive(result_bytes))
        assert len(messages) == 4
        assert isinstance(messages[0], RowDescription)
        assert isinstance(messages[1], DataRow)
        assert isinstance(messages[2], CommandComplete)
        assert isinstance(messages[3], ReadyForQuery)
        assert client.phase == ConnectionPhase.READY
