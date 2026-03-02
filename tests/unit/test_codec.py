"""Unit tests for BackendMessageDecoder and FrontendMessageDecoder."""

import struct

import pytest

from pygwire.codec import BackendMessageDecoder, FrontendMessageDecoder
from pygwire.constants import ProtocolVersion, TransactionStatus
from pygwire.messages import (
    AuthenticationOk,
    CancelRequest,
    CommandComplete,
    DataRow,
    PasswordMessage,
    ProtocolError,
    Query,
    ReadyForQuery,
    RowDescription,
    SSLRequest,
    StartupMessage,
)


class TestBackendMessageDecoder:
    """Tests for BackendMessageDecoder (used by clients, decodes server messages)."""

    def test_default_initialization(self):
        """Test decoder initializes with default settings."""
        decoder = BackendMessageDecoder()
        assert not decoder.in_startup
        assert decoder.buffered == 0

    def test_startup_mode_initialization(self):
        """Test decoder initializes in startup mode when requested."""
        decoder = FrontendMessageDecoder(startup=True)
        assert decoder.in_startup

    def test_buffered_reflects_unprocessed_data(self):
        """Test buffered property returns correct byte count."""
        decoder = BackendMessageDecoder()
        assert decoder.buffered == 0

        # Feed incomplete message (header only, no payload)
        decoder.feed(b"Z\x00\x00\x00\x05")  # ReadyForQuery with incomplete payload
        assert decoder.buffered == 5

    def test_clear_discards_all_data(self):
        """Test clear() removes all buffered data and messages."""
        decoder = BackendMessageDecoder()
        msg = ReadyForQuery(status=TransactionStatus.IDLE)
        decoder.feed(msg.to_wire())
        decoder.feed(b"Z\x00\x00\x00\x05")  # Incomplete message

        decoder.clear()
        assert decoder.buffered == 0
        assert decoder.read() is None

    def test_decode_authentication_ok(self):
        """Test decoding AuthenticationOk message."""
        decoder = BackendMessageDecoder()
        msg = AuthenticationOk()

        decoder.feed(msg.to_wire())

        decoded = decoder.read()
        assert isinstance(decoded, AuthenticationOk)

    def test_decode_ready_for_query(self):
        """Test decoding ReadyForQuery message."""
        decoder = BackendMessageDecoder()
        msg = ReadyForQuery(status=TransactionStatus.IDLE)

        decoder.feed(msg.to_wire())

        decoded = decoder.read()
        assert isinstance(decoded, ReadyForQuery)
        assert decoded.status == TransactionStatus.IDLE

    def test_decode_command_complete(self):
        """Test decoding CommandComplete message."""
        decoder = BackendMessageDecoder()
        msg = CommandComplete(tag="SELECT 42")

        decoder.feed(msg.to_wire())

        decoded = decoder.read()
        assert isinstance(decoded, CommandComplete)
        assert decoded.tag == "SELECT 42"

    def test_decode_data_row_with_values(self):
        """Test decoding DataRow with actual values."""
        decoder = BackendMessageDecoder()
        msg = DataRow(columns=[b"value1", b"value2", b"value3"])

        decoder.feed(msg.to_wire())

        decoded = decoder.read()
        assert isinstance(decoded, DataRow)
        assert decoded.columns == [b"value1", b"value2", b"value3"]

    def test_decode_data_row_with_nulls(self):
        """Test decoding DataRow with NULL values."""
        decoder = BackendMessageDecoder()
        msg = DataRow(columns=[b"value1", None, b"value3"])

        decoder.feed(msg.to_wire())

        decoded = decoder.read()
        assert isinstance(decoded, DataRow)
        assert decoded.columns[0] == b"value1"
        assert decoded.columns[1] is None
        assert decoded.columns[2] == b"value3"

    def test_decode_row_description_empty(self):
        """Test decoding empty RowDescription."""
        decoder = BackendMessageDecoder()
        msg = RowDescription(fields=[])

        decoder.feed(msg.to_wire())

        decoded = decoder.read()
        assert isinstance(decoded, RowDescription)
        assert decoded.fields == []


class TestFrontendMessageDecoder:
    """Tests for FrontendMessageDecoder (used by servers, decodes client messages)."""

    def test_default_initialization(self):
        """Test decoder initializes with default settings."""
        decoder = FrontendMessageDecoder()
        assert not decoder.in_startup
        assert decoder.buffered == 0

    def test_startup_mode_initialization(self):
        """Test decoder initializes in startup mode when requested."""
        decoder = FrontendMessageDecoder(startup=True)
        assert decoder.in_startup

    def test_decode_query_message(self):
        """Test decoding Query message."""
        decoder = FrontendMessageDecoder()
        msg = Query(query_string="SELECT * FROM users")

        decoder.feed(msg.to_wire())

        decoded = decoder.read()
        assert isinstance(decoded, Query)
        assert decoded.query_string == "SELECT * FROM users"

    def test_decode_password_message(self):
        """Test decoding PasswordMessage."""
        decoder = FrontendMessageDecoder()
        msg = PasswordMessage(password="secret123")

        decoder.feed(msg.to_wire())

        decoded = decoder.read()
        assert isinstance(decoded, PasswordMessage)
        assert decoded.password == "secret123"

    def test_decode_startup_message(self):
        """Test decoding StartupMessage."""
        decoder = FrontendMessageDecoder(startup=True)
        msg = StartupMessage(params={"user": "testuser", "database": "testdb"})

        decoder.feed(msg.to_wire())

        decoded = decoder.read()
        assert isinstance(decoded, StartupMessage)
        assert decoded.params["user"] == "testuser"
        assert decoded.params["database"] == "testdb"


class TestDecoderFeedAndRead:
    """Tests for feed() and read() methods."""

    def test_feed_empty_data(self):
        """Test feeding empty data is a no-op."""
        decoder = BackendMessageDecoder()
        decoder.feed(b"")
        assert decoder.buffered == 0
        assert decoder.read() is None

    def test_feed_complete_message(self):
        """Test feeding a complete message."""
        decoder = FrontendMessageDecoder()
        msg = Query(query_string="SELECT 1")
        decoder.feed(msg.to_wire())

        decoded = decoder.read()
        assert isinstance(decoded, Query)
        assert decoded.query_string == "SELECT 1"
        assert decoder.read() is None

    def test_feed_partial_message(self):
        """Test feeding partial message data."""
        decoder = FrontendMessageDecoder()
        wire = Query(query_string="SELECT 1").to_wire()

        # Feed only half of the message
        decoder.feed(wire[:5])
        assert decoder.read() is None  # Not enough data yet
        assert decoder.buffered == 5

        # Feed the rest
        decoder.feed(wire[5:])
        decoded = decoder.read()
        assert isinstance(decoded, Query)
        assert decoded.query_string == "SELECT 1"

    def test_feed_multiple_messages(self):
        """Test feeding multiple messages at once."""
        decoder = FrontendMessageDecoder()
        msg1 = Query(query_string="SELECT 1")
        msg2 = Query(query_string="SELECT 2")

        decoder.feed(msg1.to_wire() + msg2.to_wire())

        decoded1 = decoder.read()
        assert isinstance(decoded1, Query)
        assert decoded1.query_string == "SELECT 1"

        decoded2 = decoder.read()
        assert isinstance(decoded2, Query)
        assert decoded2.query_string == "SELECT 2"

        assert decoder.read() is None

    def test_feed_with_memoryview(self):
        """Test feeding data as memoryview."""
        decoder = FrontendMessageDecoder()
        msg = Query(query_string="SELECT 1")
        wire = msg.to_wire()

        decoder.feed(memoryview(wire))
        decoded = decoder.read()
        assert isinstance(decoded, Query)
        assert decoded.query_string == "SELECT 1"

    def test_feed_with_bytearray(self):
        """Test feeding data as bytearray."""
        decoder = FrontendMessageDecoder()
        msg = Query(query_string="SELECT 1")
        wire = bytearray(msg.to_wire())

        decoder.feed(wire)
        decoded = decoder.read()
        assert isinstance(decoded, Query)
        assert decoded.query_string == "SELECT 1"

    def test_read_all_returns_all_messages(self):
        """Test read_all() returns all decoded messages."""
        decoder = FrontendMessageDecoder()
        msg1 = Query(query_string="SELECT 1")
        msg2 = Query(query_string="SELECT 2")

        decoder.feed(msg1.to_wire() + msg2.to_wire())

        messages = decoder.read_all()
        assert len(messages) == 2
        assert isinstance(messages[0], Query)
        assert isinstance(messages[1], Query)
        assert decoder.read() is None  # Queue is drained

    def test_iteration_interface(self):
        """Test decoder can be iterated."""
        decoder = FrontendMessageDecoder()
        msg1 = Query(query_string="SELECT 1")
        msg2 = Query(query_string="SELECT 2")

        decoder.feed(msg1.to_wire() + msg2.to_wire())

        messages = list(decoder)
        assert len(messages) == 2
        assert all(isinstance(m, Query) for m in messages)


class TestStartupPhase:
    """Tests for startup phase (identifier-less messages)."""

    def test_decode_ssl_request(self):
        """Test decoding SSLRequest."""
        decoder = FrontendMessageDecoder(startup=True)
        msg = SSLRequest()

        decoder.feed(msg.to_wire())

        decoded = decoder.read()
        assert isinstance(decoded, SSLRequest)

    def test_decode_cancel_request(self):
        """Test decoding CancelRequest."""
        decoder = FrontendMessageDecoder(startup=True)
        msg = CancelRequest(process_id=12345, secret_key=b"test")

        decoder.feed(msg.to_wire())

        decoded = decoder.read()
        assert isinstance(decoded, CancelRequest)
        assert decoded.process_id == 12345
        assert decoded.secret_key == b"test"

    def test_startup_transitions_to_standard_after_startup_message(self):
        """Test decoder exits startup mode after StartupMessage."""
        decoder = FrontendMessageDecoder(startup=True)
        startup_msg = StartupMessage(params={"user": "test"})

        assert decoder.in_startup
        decoder.feed(startup_msg.to_wire())
        decoder.read()  # Consume the message

        # After StartupMessage, decoder should be in standard mode
        assert not decoder.in_startup

        # Now can decode standard messages
        query_msg = Query(query_string="SELECT 1")
        decoder.feed(query_msg.to_wire())
        decoded = decoder.read()
        assert isinstance(decoded, Query)

    def test_startup_message_too_short_raises_error(self):
        """Test that short startup message raises ProtocolError."""
        decoder = FrontendMessageDecoder(startup=True)
        # Feed a message with length that's too short for version code
        # Error is raised during feed() not read()
        with pytest.raises(ProtocolError):
            decoder.feed(b"\x00\x00\x00\x06\x00\x01")  # Length 6, but payload only 2 bytes

    def test_unknown_startup_version_raises_error(self):
        """Test unknown startup version code raises ProtocolError."""
        decoder = FrontendMessageDecoder(startup=True)
        # Create message with unknown version code
        wire = b"\x00\x00\x00\x08\xff\xff\xff\xff"  # Invalid version code

        # Error is raised during feed() not read()
        with pytest.raises(ProtocolError):
            decoder.feed(wire)


class TestDecoderErrors:
    """Tests for error handling in decoders."""

    def test_unknown_backend_message_identifier(self):
        """Test that unknown backend message identifier raises error."""
        decoder = BackendMessageDecoder()
        # Create message with invalid identifier 'X' (which is frontend Terminate)
        # But we're using BackendMessageDecoder, so we expect backend messages
        wire = b"X\x00\x00\x00\x04"  # Invalid for backend

        # Error is raised during feed() not read()
        with pytest.raises(ProtocolError):
            decoder.feed(wire)

    def test_unknown_frontend_message_identifier(self):
        """Test that unknown frontend message identifier raises error."""
        decoder = FrontendMessageDecoder()
        # Create message with invalid identifier 'Z' (which is backend ReadyForQuery)
        # But we're using FrontendMessageDecoder, so we expect frontend messages
        wire = b"Z\x00\x00\x00\x05I"

        # Error is raised during feed() not read()
        with pytest.raises(ProtocolError):
            decoder.feed(wire)

    def test_truly_unknown_identifier_raises_error(self):
        """Test that a completely unknown identifier raises error."""
        decoder = BackendMessageDecoder()
        # Use identifier that's not used by either side
        wire = b"x\x00\x00\x00\x04"

        # Error is raised during feed() not read()
        with pytest.raises(ProtocolError):
            decoder.feed(wire)


class TestBufferManagement:
    """Tests for internal buffer management and compaction."""

    def test_buffer_compaction_after_threshold(self):
        """Test that buffer is compacted after processing many messages."""
        decoder = FrontendMessageDecoder()

        # Feed many small messages to trigger compaction
        for i in range(100):
            msg = Query(query_string=f"SELECT {i}")
            decoder.feed(msg.to_wire())

        # Consume all messages
        messages = decoder.read_all()
        assert len(messages) == 100

        # Buffer should be mostly empty now (compacted)
        assert decoder.buffered == 0

    def test_mixed_complete_and_incomplete_messages(self):
        """Test handling mix of complete and incomplete messages."""
        decoder = FrontendMessageDecoder()

        msg1 = Query(query_string="SELECT 1")
        msg2 = Query(query_string="SELECT 2")
        wire1 = msg1.to_wire()
        wire2 = msg2.to_wire()

        # Feed first complete message + partial second message
        decoder.feed(wire1 + wire2[:5])

        # Should decode first message
        decoded = decoder.read()
        assert isinstance(decoded, Query)
        assert decoded.query_string == "SELECT 1"

        # Second message not ready yet
        assert decoder.read() is None
        assert decoder.buffered == 5

        # Feed rest of second message
        decoder.feed(wire2[5:])
        decoded = decoder.read()
        assert isinstance(decoded, Query)
        assert decoded.query_string == "SELECT 2"

    def test_many_messages_in_single_feed(self):
        """Test decoding many messages fed at once."""
        decoder = FrontendMessageDecoder()

        messages = []
        wire_data = b""
        for i in range(50):
            msg = Query(query_string=f"SELECT {i}")
            messages.append(msg)
            wire_data += msg.to_wire()

        decoder.feed(wire_data)

        decoded_messages = decoder.read_all()
        assert len(decoded_messages) == 50
        for i, msg in enumerate(decoded_messages):
            assert isinstance(msg, Query)
            assert msg.query_string == f"SELECT {i}"

    def test_incomplete_header_waits_for_more_data(self):
        """Test that incomplete header doesn't decode yet."""
        decoder = FrontendMessageDecoder()
        # Feed only 3 bytes (header is 5: 1 byte id + 4 bytes length)
        decoder.feed(b"Q\x00\x00")

        assert decoder.read() is None
        assert decoder.buffered == 3

    def test_incomplete_payload_waits_for_more_data(self):
        """Test that incomplete payload doesn't decode yet."""
        decoder = FrontendMessageDecoder()
        msg = Query(query_string="SELECT 1")
        wire = msg.to_wire()

        # Feed all but last byte
        decoder.feed(wire[:-1])
        assert decoder.read() is None


class TestRoundTrip:
    """Round-trip tests: encode then decode."""

    def test_query_round_trip(self):
        """Test Query message round-trip."""
        original = Query(query_string="SELECT * FROM users WHERE id = 42")
        wire = original.to_wire()

        decoder = FrontendMessageDecoder()
        decoder.feed(wire)
        decoded = decoder.read()

        assert isinstance(decoded, Query)
        assert decoded.query_string == original.query_string

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
        wire = original.to_wire()

        decoder = FrontendMessageDecoder(startup=True)
        decoder.feed(wire)
        decoded = decoder.read()

        assert isinstance(decoded, StartupMessage)
        assert decoded.params == original.params

    def test_data_row_with_nulls_round_trip(self):
        """Test DataRow with NULL values round-trip."""
        original = DataRow(columns=[b"value1", None, b"value3", None, b"value5"])
        wire = original.to_wire()

        decoder = BackendMessageDecoder()
        decoder.feed(wire)
        decoded = decoder.read()

        assert isinstance(decoded, DataRow)
        assert decoded.columns == original.columns

    def test_command_complete_round_trip(self):
        """Test CommandComplete round-trip."""
        original = CommandComplete(tag="INSERT 0 1")
        wire = original.to_wire()

        decoder = BackendMessageDecoder()
        decoder.feed(wire)
        decoded = decoder.read()

        assert isinstance(decoded, CommandComplete)
        assert decoded.tag == original.tag

    def test_empty_message_round_trip(self):
        """Test message with no payload round-trip."""
        original = AuthenticationOk()
        wire = original.to_wire()

        decoder = BackendMessageDecoder()
        decoder.feed(wire)
        decoded = decoder.read()

        assert isinstance(decoded, AuthenticationOk)


class TestEdgeCases:
    """Edge case tests for decoders."""

    def test_empty_query_string(self):
        """Test decoding Query with empty string."""
        decoder = FrontendMessageDecoder()
        msg = Query(query_string="")

        decoder.feed(msg.to_wire())
        decoded = decoder.read()

        assert isinstance(decoded, Query)
        assert decoded.query_string == ""

    def test_very_large_message(self):
        """Test decoding very large message."""
        decoder = FrontendMessageDecoder()
        large_query = "SELECT * FROM table WHERE " + " OR ".join(
            [f"col{i} = {i}" for i in range(1000)]
        )
        msg = Query(query_string=large_query)

        decoder.feed(msg.to_wire())
        decoded = decoder.read()

        assert isinstance(decoded, Query)
        assert decoded.query_string == large_query

    def test_unicode_in_query(self):
        """Test decoding Query with Unicode characters."""
        decoder = FrontendMessageDecoder()
        msg = Query(query_string="SELECT '你好世界' AS greeting")

        decoder.feed(msg.to_wire())
        decoded = decoder.read()

        assert isinstance(decoded, Query)
        assert decoded.query_string == "SELECT '你好世界' AS greeting"

    def test_byte_at_a_time_feeding(self):
        """Test feeding message one byte at a time."""
        decoder = FrontendMessageDecoder()
        msg = Query(query_string="SELECT 1")
        wire = msg.to_wire()

        # Feed one byte at a time
        for byte in wire[:-1]:
            decoder.feed(bytes([byte]))
            assert decoder.read() is None  # Not complete yet

        # Feed last byte
        decoder.feed(bytes([wire[-1]]))
        decoded = decoder.read()
        assert isinstance(decoded, Query)
        assert decoded.query_string == "SELECT 1"


class TestMaxMessageSize:
    """Tests for max_message_size bounds checking."""

    def test_standard_message_exceeding_max_size_raises_error(self):
        """Test that a standard message with length exceeding max_message_size raises ProtocolError."""
        decoder = BackendMessageDecoder(max_message_size=64)
        # Craft a message header claiming length of 1000 bytes (identifier 'R' + length field)
        wire = b"R" + struct.pack("!I", 1000)
        with pytest.raises(ProtocolError, match="exceeds maximum allowed size"):
            decoder.feed(wire)

    def test_startup_message_exceeding_max_size_raises_error(self):
        """Test that a startup message with length exceeding max_message_size raises ProtocolError."""
        decoder = FrontendMessageDecoder(startup=True, max_message_size=64)
        # Craft a startup message header claiming length of 1000 bytes
        wire = struct.pack("!I", 1000)
        with pytest.raises(
            ProtocolError, match="Startup message length.*exceeds maximum allowed size"
        ):
            decoder.feed(wire)

    def test_message_within_max_size_decodes_successfully(self):
        """Test that messages within the max size limit decode normally."""
        decoder = FrontendMessageDecoder(max_message_size=4096)
        msg = Query(query_string="SELECT 1")
        decoder.feed(msg.to_wire())
        decoded = decoder.read()
        assert isinstance(decoded, Query)
        assert decoded.query_string == "SELECT 1"

    def test_startup_message_within_max_size_decodes_successfully(self):
        """Test that startup messages within the max size limit decode normally."""
        decoder = FrontendMessageDecoder(startup=True, max_message_size=4096)
        msg = StartupMessage(params={"user": "test"})
        decoder.feed(msg.to_wire())
        decoded = decoder.read()
        assert isinstance(decoded, StartupMessage)

    def test_v3_2_startup_message_decodes_successfully(self):
        """Test that v3.2 StartupMessage (PG 18+) can be decoded."""
        decoder = FrontendMessageDecoder(startup=True)

        # Create a v3.2 startup message manually
        params = {"user": "postgres", "database": "testdb"}
        buf = bytearray()
        # Version code
        buf.extend(struct.pack("!I", ProtocolVersion.V3_2))
        # Parameters
        for key, value in params.items():
            buf.extend(key.encode("utf-8"))
            buf.append(0)
            buf.extend(value.encode("utf-8"))
            buf.append(0)
        buf.append(0)  # final null terminator

        # Add length header for wire format
        length = len(buf) + 4  # length includes itself
        wire = struct.pack("!I", length) + buf

        decoder.feed(wire)
        decoded = decoder.read()
        assert isinstance(decoded, StartupMessage)
        assert decoded.params == params
        assert decoded.protocol_version == ProtocolVersion.V3_2

    def test_max_message_size_boundary_exactly_at_limit(self):
        """Test that a message whose length equals max_message_size is accepted."""
        msg = Query(query_string="SELECT 1")
        wire = msg.to_wire()
        # The length field value is total_wire_length - 1 (excludes the identifier byte)
        length_field = len(wire) - 1
        decoder = FrontendMessageDecoder(max_message_size=length_field)
        decoder.feed(wire)
        decoded = decoder.read()
        assert isinstance(decoded, Query)

    def test_max_message_size_boundary_one_below_limit(self):
        """Test that a message whose length is one over max_message_size is rejected."""
        msg = Query(query_string="SELECT 1")
        wire = msg.to_wire()
        length_field = len(wire) - 1
        decoder = FrontendMessageDecoder(max_message_size=length_field - 1)
        with pytest.raises(ProtocolError, match="exceeds maximum allowed size"):
            decoder.feed(wire)

    def test_huge_declared_length_rejected_without_buffering(self):
        """Test that a 4 GB declared length is rejected immediately on header arrival."""
        decoder = BackendMessageDecoder(max_message_size=1024)
        # Craft header with 0xFFFFFFFF length — only 5 bytes sent, not 4 GB
        wire = b"R" + struct.pack("!I", 0xFFFFFFFF)
        with pytest.raises(ProtocolError, match="exceeds maximum allowed size"):
            decoder.feed(wire)
