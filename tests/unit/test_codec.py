"""Unit tests for Connection-based decoding (formerly standalone decoders).

Tests verify that the Connection classes correctly decode messages from wire
format, handling startup framing, standard framing, SSL/GSS negotiation,
and SASL authentication dispatch.
"""

import struct

import pytest

from pygwire.connection import BackendConnection, FrontendConnection
from pygwire.constants import ProtocolVersion, TransactionStatus
from pygwire.exceptions import ProtocolError
from pygwire.messages import (
    AuthenticationOk,
    AuthenticationSASL,
    AuthenticationSASLContinue,
    CancelRequest,
    CommandComplete,
    DataRow,
    GSSResponse,
    PasswordMessage,
    Query,
    ReadyForQuery,
    RowDescription,
    SASLInitialResponse,
    SASLResponse,
    SSLRequest,
    SSLResponse,
    StartupMessage,
)
from pygwire.state_machine import ConnectionPhase


class TestBackendDecoding:
    """Tests for decoding backend (server) messages via FrontendConnection."""

    def test_default_initialization(self):
        """Test connection initializes in STARTUP phase."""
        conn = FrontendConnection()
        assert conn.phase == ConnectionPhase.STARTUP
        assert conn.is_active

    def test_decode_authentication_ok(self):
        """Test decoding AuthenticationOk message."""
        conn = FrontendConnection()
        conn.send(StartupMessage(params={"user": "test"}))

        msg = AuthenticationOk()
        msgs = list(conn.receive(msg.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], AuthenticationOk)

    def test_decode_ready_for_query(self):
        """Test decoding ReadyForQuery message."""
        conn = FrontendConnection()
        conn.send(StartupMessage(params={"user": "test"}))

        auth_wire = AuthenticationOk().to_wire()
        ready_wire = ReadyForQuery(status=TransactionStatus.IDLE).to_wire()
        msgs = list(conn.receive(auth_wire + ready_wire))

        assert len(msgs) == 2
        assert isinstance(msgs[1], ReadyForQuery)
        assert msgs[1].status == TransactionStatus.IDLE

    def test_decode_command_complete(self):
        """Test decoding CommandComplete message."""
        conn = FrontendConnection(initial_phase=ConnectionPhase.SIMPLE_QUERY, strict=False)
        msg = CommandComplete(tag="SELECT 42")

        msgs = list(conn.receive(msg.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], CommandComplete)
        assert msgs[0].tag == "SELECT 42"

    def test_decode_data_row_with_values(self):
        """Test decoding DataRow with actual values."""
        conn = FrontendConnection(initial_phase=ConnectionPhase.SIMPLE_QUERY, strict=False)
        msg = DataRow(columns=[b"value1", b"value2", b"value3"])

        msgs = list(conn.receive(msg.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], DataRow)
        assert msgs[0].columns == [b"value1", b"value2", b"value3"]

    def test_decode_data_row_with_nulls(self):
        """Test decoding DataRow with NULL values."""
        conn = FrontendConnection(initial_phase=ConnectionPhase.SIMPLE_QUERY, strict=False)
        msg = DataRow(columns=[b"value1", None, b"value3"])

        msgs = list(conn.receive(msg.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], DataRow)
        assert msgs[0].columns[0] == b"value1"
        assert msgs[0].columns[1] is None
        assert msgs[0].columns[2] == b"value3"

    def test_decode_row_description_empty(self):
        """Test decoding empty RowDescription."""
        conn = FrontendConnection(initial_phase=ConnectionPhase.SIMPLE_QUERY, strict=False)
        msg = RowDescription(fields=[])

        msgs = list(conn.receive(msg.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], RowDescription)
        assert msgs[0].fields == []


class TestFrontendDecoding:
    """Tests for decoding frontend (client) messages via BackendConnection."""

    def test_default_initialization(self):
        """Test connection initializes in STARTUP phase."""
        conn = BackendConnection()
        assert conn.phase == ConnectionPhase.STARTUP

    def test_decode_query_message(self):
        """Test decoding Query message."""
        conn = BackendConnection(initial_phase=ConnectionPhase.READY)
        msg = Query(query_string="SELECT * FROM users")

        msgs = list(conn.receive(msg.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], Query)
        assert msgs[0].query_string == "SELECT * FROM users"

    def test_decode_password_message(self):
        """Test decoding PasswordMessage."""
        conn = BackendConnection(initial_phase=ConnectionPhase.AUTHENTICATING, strict=False)
        msg = PasswordMessage(password="secret123")

        msgs = list(conn.receive(msg.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], PasswordMessage)
        assert msgs[0].password == "secret123"

    def test_decode_startup_message(self):
        """Test decoding StartupMessage."""
        conn = BackendConnection()
        msg = StartupMessage(params={"user": "testuser", "database": "testdb"})

        msgs = list(conn.receive(msg.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], StartupMessage)
        assert msgs[0].params["user"] == "testuser"
        assert msgs[0].params["database"] == "testdb"


class TestFeedAndRead:
    """Tests for feed/receive mechanics."""

    def test_feed_empty_data(self):
        """Test feeding empty data is a no-op."""
        conn = BackendConnection(initial_phase=ConnectionPhase.READY)
        msgs = list(conn.receive(b""))
        assert msgs == []

    def test_feed_complete_message(self):
        """Test feeding a complete message."""
        conn = BackendConnection(initial_phase=ConnectionPhase.READY)
        msg = Query(query_string="SELECT 1")

        msgs = list(conn.receive(msg.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], Query)
        assert msgs[0].query_string == "SELECT 1"

    def test_feed_partial_message(self):
        """Test feeding partial message data."""
        conn = BackendConnection(initial_phase=ConnectionPhase.READY)
        wire = Query(query_string="SELECT 1").to_wire()

        # Feed only half of the message
        msgs = list(conn.receive(wire[:5]))
        assert msgs == []  # Not enough data yet

        # Feed the rest
        msgs = list(conn.receive(wire[5:]))
        assert len(msgs) == 1
        assert isinstance(msgs[0], Query)
        assert msgs[0].query_string == "SELECT 1"

    def test_feed_multiple_messages(self):
        """Test feeding multiple messages at once."""
        conn = BackendConnection(initial_phase=ConnectionPhase.SIMPLE_QUERY, strict=False)
        msg1 = Query(query_string="SELECT 1")
        msg2 = Query(query_string="SELECT 2")

        msgs = list(conn.receive(msg1.to_wire() + msg2.to_wire()))
        assert len(msgs) == 2
        assert msgs[0].query_string == "SELECT 1"
        assert msgs[1].query_string == "SELECT 2"

    def test_feed_with_memoryview(self):
        """Test feeding data as memoryview."""
        conn = BackendConnection(initial_phase=ConnectionPhase.READY)
        wire = Query(query_string="SELECT 1").to_wire()

        msgs = list(conn.receive(memoryview(wire)))
        assert len(msgs) == 1
        assert isinstance(msgs[0], Query)

    def test_feed_with_bytearray(self):
        """Test feeding data as bytearray."""
        conn = BackendConnection(initial_phase=ConnectionPhase.READY)
        wire = bytearray(Query(query_string="SELECT 1").to_wire())

        msgs = list(conn.receive(wire))
        assert len(msgs) == 1
        assert isinstance(msgs[0], Query)


class TestStartupPhase:
    """Tests for startup phase (identifier-less messages)."""

    def test_decode_ssl_request(self):
        """Test decoding SSLRequest."""
        conn = BackendConnection()
        msg = SSLRequest()

        msgs = list(conn.receive(msg.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], SSLRequest)

    def test_decode_cancel_request(self):
        """Test decoding CancelRequest."""
        conn = BackendConnection()
        msg = CancelRequest(process_id=12345, secret_key=b"test")

        msgs = list(conn.receive(msg.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], CancelRequest)
        assert msgs[0].process_id == 12345
        assert msgs[0].secret_key == b"test"

    def test_startup_transitions_to_standard_after_startup_message(self):
        """Test connection exits startup framing after StartupMessage."""
        conn = BackendConnection()

        startup_msg = StartupMessage(params={"user": "test"})
        msgs = list(conn.receive(startup_msg.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], StartupMessage)

        # After StartupMessage, send auth and server should decode standard messages
        conn.send(AuthenticationOk())
        conn.send(ReadyForQuery(status=TransactionStatus.IDLE))

        # Now receive standard messages
        query_msg = Query(query_string="SELECT 1")
        msgs = list(conn.receive(query_msg.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], Query)

    def test_startup_message_too_short_raises_error(self):
        """Test that short startup message raises ProtocolError."""
        conn = BackendConnection()
        with pytest.raises(ProtocolError):
            list(conn.receive(b"\x00\x00\x00\x06\x00\x01"))

    def test_unknown_startup_version_raises_error(self):
        """Test unknown startup version code raises ProtocolError."""
        conn = BackendConnection()
        wire = b"\x00\x00\x00\x08\xff\xff\xff\xff"
        with pytest.raises(ProtocolError):
            list(conn.receive(wire))


class TestSSLNegotiation:
    """Tests for SSL negotiation phase."""

    def test_ssl_response_accepted(self):
        """Test decoding accepted SSL response."""
        conn = FrontendConnection()
        conn.send(SSLRequest())
        assert conn.phase == ConnectionPhase.SSL_NEGOTIATION

        msgs = list(conn.receive(b"S"))
        assert len(msgs) == 1
        assert isinstance(msgs[0], SSLResponse)
        assert msgs[0].accepted is True
        assert conn.phase == ConnectionPhase.STARTUP

    def test_ssl_response_not_accepted(self):
        """Test decoding not-accepted SSL response."""
        conn = FrontendConnection()
        conn.send(SSLRequest())

        msgs = list(conn.receive(b"N"))
        assert len(msgs) == 1
        assert isinstance(msgs[0], SSLResponse)
        assert msgs[0].accepted is False
        assert conn.phase == ConnectionPhase.STARTUP

    def test_gss_response_accepted(self):
        """Test decoding accepted GSS response."""
        from pygwire.messages import GSSEncRequest

        conn = FrontendConnection()
        conn.send(GSSEncRequest())
        assert conn.phase == ConnectionPhase.GSS_NEGOTIATION

        msgs = list(conn.receive(b"G"))
        assert len(msgs) == 1
        assert isinstance(msgs[0], GSSResponse)
        assert msgs[0].accepted is True
        assert conn.phase == ConnectionPhase.STARTUP


class TestSASLDispatch:
    """Tests for SASL-aware 'p' identifier dispatch."""

    def test_sasl_initial_response_decoded(self):
        """Test that 'p' message is decoded as SASLInitialResponse during SASL initial phase."""
        conn = BackendConnection()

        # Startup
        list(conn.receive(StartupMessage(params={"user": "test"}).to_wire()))

        # Server sends SASL auth request
        conn.send(AuthenticationSASL(mechanisms=["SCRAM-SHA-256"]))
        assert conn.phase == ConnectionPhase.AUTHENTICATING_SASL_INITIAL

        # Client sends SASLInitialResponse (identifier 'p')
        sir = SASLInitialResponse(mechanism="SCRAM-SHA-256", data=b"client-first")
        msgs = list(conn.receive(sir.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], SASLInitialResponse)
        assert msgs[0].mechanism == "SCRAM-SHA-256"
        assert msgs[0].data == b"client-first"

    def test_sasl_response_decoded(self):
        """Test that 'p' message is decoded as SASLResponse during SASL continue phase."""
        conn = BackendConnection()

        # Startup + SASL handshake
        list(conn.receive(StartupMessage(params={"user": "test"}).to_wire()))
        conn.send(AuthenticationSASL(mechanisms=["SCRAM-SHA-256"]))
        list(
            conn.receive(
                SASLInitialResponse(mechanism="SCRAM-SHA-256", data=b"client-first").to_wire()
            )
        )
        conn.send(AuthenticationSASLContinue(data=b"server-first"))
        assert conn.phase == ConnectionPhase.AUTHENTICATING_SASL_CONTINUE

        # Client sends SASLResponse (identifier 'p')
        sr = SASLResponse(data=b"client-final")
        msgs = list(conn.receive(sr.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], SASLResponse)
        assert msgs[0].data == b"client-final"

    def test_password_message_in_authenticating_phase(self):
        """Test that 'p' message is decoded as PasswordMessage in AUTHENTICATING phase."""
        from pygwire.messages import AuthenticationCleartextPassword

        conn = BackendConnection()

        # Startup + cleartext auth
        list(conn.receive(StartupMessage(params={"user": "test"}).to_wire()))
        conn.send(AuthenticationCleartextPassword())
        assert conn.phase == ConnectionPhase.AUTHENTICATING

        # Client sends PasswordMessage (identifier 'p')
        pm = PasswordMessage(password="secret")
        msgs = list(conn.receive(pm.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], PasswordMessage)
        assert msgs[0].password == "secret"


class TestDecoderErrors:
    """Tests for error handling in decoders."""

    def test_unknown_backend_message_identifier(self):
        """Test that unknown backend message identifier raises error."""
        conn = FrontendConnection(initial_phase=ConnectionPhase.READY, strict=False)
        wire = b"x\x00\x00\x00\x04"
        with pytest.raises(ProtocolError):
            list(conn.receive(wire))

    def test_unknown_frontend_message_identifier(self):
        """Test that unknown frontend message identifier raises error."""
        conn = BackendConnection(initial_phase=ConnectionPhase.READY, strict=False)
        wire = b"Z\x00\x00\x00\x05I"  # 'Z' is backend ReadyForQuery, not a frontend message
        with pytest.raises(ProtocolError):
            list(conn.receive(wire))


class TestBufferManagement:
    """Tests for internal buffer management and compaction."""

    def test_buffer_compaction_after_threshold(self):
        """Test that buffer is compacted after processing many messages."""
        conn = BackendConnection(initial_phase=ConnectionPhase.SIMPLE_QUERY, strict=False)

        for i in range(100):
            msg = Query(query_string=f"SELECT {i}")
            list(conn.receive(msg.to_wire()))

    def test_mixed_complete_and_incomplete_messages(self):
        """Test handling mix of complete and incomplete messages."""
        conn = BackendConnection(initial_phase=ConnectionPhase.SIMPLE_QUERY, strict=False)

        msg1 = Query(query_string="SELECT 1")
        msg2 = Query(query_string="SELECT 2")
        wire1 = msg1.to_wire()
        wire2 = msg2.to_wire()

        # Feed first complete message + partial second message
        msgs = list(conn.receive(wire1 + wire2[:5]))
        assert len(msgs) == 1
        assert msgs[0].query_string == "SELECT 1"

        # Feed rest of second message
        msgs = list(conn.receive(wire2[5:]))
        assert len(msgs) == 1
        assert msgs[0].query_string == "SELECT 2"

    def test_byte_at_a_time_feeding(self):
        """Test feeding message one byte at a time."""
        conn = BackendConnection(initial_phase=ConnectionPhase.READY)
        msg = Query(query_string="SELECT 1")
        wire = msg.to_wire()

        # Feed one byte at a time
        for byte in wire[:-1]:
            msgs = list(conn.receive(bytes([byte])))
            assert msgs == []

        # Feed last byte
        msgs = list(conn.receive(bytes([wire[-1]])))
        assert len(msgs) == 1
        assert isinstance(msgs[0], Query)
        assert msgs[0].query_string == "SELECT 1"


class TestRoundTrip:
    """Round-trip tests: encode then decode."""

    def test_query_round_trip(self):
        """Test Query message round-trip."""
        original = Query(query_string="SELECT * FROM users WHERE id = 42")
        conn = BackendConnection(initial_phase=ConnectionPhase.READY)

        msgs = list(conn.receive(original.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], Query)
        assert msgs[0].query_string == original.query_string

    def test_startup_message_round_trip(self):
        """Test StartupMessage round-trip."""
        original = StartupMessage(
            params={
                "user": "testuser",
                "database": "testdb",
                "application_name": "myapp",
                "client_encoding": "UTF8",
            }
        )
        conn = BackendConnection()

        msgs = list(conn.receive(original.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], StartupMessage)
        assert msgs[0].params == original.params

    def test_data_row_with_nulls_round_trip(self):
        """Test DataRow with NULL values round-trip."""
        original = DataRow(columns=[b"value1", None, b"value3", None, b"value5"])
        conn = FrontendConnection(initial_phase=ConnectionPhase.SIMPLE_QUERY, strict=False)

        msgs = list(conn.receive(original.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], DataRow)
        assert msgs[0].columns == original.columns


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_query_string(self):
        """Test decoding Query with empty string."""
        conn = BackendConnection(initial_phase=ConnectionPhase.READY)
        msg = Query(query_string="")

        msgs = list(conn.receive(msg.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], Query)
        assert msgs[0].query_string == ""

    def test_very_large_message(self):
        """Test decoding very large message."""
        conn = BackendConnection(initial_phase=ConnectionPhase.READY)
        large_query = "SELECT * FROM table WHERE " + " OR ".join(
            [f"col{i} = {i}" for i in range(1000)]
        )
        msg = Query(query_string=large_query)

        msgs = list(conn.receive(msg.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], Query)
        assert msgs[0].query_string == large_query

    def test_unicode_in_query(self):
        """Test decoding Query with Unicode characters."""
        conn = BackendConnection(initial_phase=ConnectionPhase.READY)
        msg = Query(query_string="SELECT '你好世界' AS greeting")

        msgs = list(conn.receive(msg.to_wire()))
        assert len(msgs) == 1
        assert isinstance(msgs[0], Query)
        assert msgs[0].query_string == "SELECT '你好世界' AS greeting"

    def test_v3_2_startup_message_decodes_successfully(self):
        """Test that v3.2 StartupMessage (PG 18+) can be decoded."""
        conn = BackendConnection()

        params = {"user": "postgres", "database": "testdb"}
        buf = bytearray()
        buf.extend(struct.pack("!I", ProtocolVersion.V3_2))
        for key, value in params.items():
            buf.extend(key.encode("utf-8"))
            buf.append(0)
            buf.extend(value.encode("utf-8"))
            buf.append(0)
        buf.append(0)

        length = len(buf) + 4
        wire = struct.pack("!I", length) + buf

        msgs = list(conn.receive(wire))
        assert len(msgs) == 1
        assert isinstance(msgs[0], StartupMessage)
        assert msgs[0].params == params
        assert msgs[0].protocol_version == ProtocolVersion.V3_2


class TestInitialPhase:
    """Tests for initial_phase parameter."""

    def test_frontend_connection_ready_phase(self):
        """Test FrontendConnection starting at READY phase."""
        conn = FrontendConnection(initial_phase=ConnectionPhase.READY)
        assert conn.phase == ConnectionPhase.READY
        assert conn.is_ready

    def test_backend_connection_ready_phase(self):
        """Test BackendConnection starting at READY phase."""
        conn = BackendConnection(initial_phase=ConnectionPhase.READY)
        assert conn.phase == ConnectionPhase.READY
        assert conn.is_ready

    def test_strict_false_does_not_raise(self):
        """Test that strict=False logs warnings instead of raising."""
        conn = FrontendConnection(initial_phase=ConnectionPhase.READY, strict=False)
        # Sending StartupMessage in READY phase is invalid
        conn.send(StartupMessage(params={"user": "test"}))  # Should not raise

    def test_strict_true_raises(self):
        """Test that strict=True raises StateMachineError."""
        from pygwire.state_machine import StateMachineError

        conn = FrontendConnection(initial_phase=ConnectionPhase.READY, strict=True)
        with pytest.raises(StateMachineError):
            conn.send(StartupMessage(params={"user": "test"}))
