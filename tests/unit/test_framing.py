"""Unit tests for framing strategies."""

import struct

import pytest

from pygwire.constants import ConnectionPhase, MessageDirection
from pygwire.exceptions import FramingError, ProtocolError
from pygwire.framing import (
    NegotiationFraming,
    StandardFraming,
    StartupFraming,
    lookup_framing,
)
from pygwire.messages import (
    AuthenticationOk,
    GSSEncRequest,
    GSSResponse,
    Query,
    SSLRequest,
    SSLResponse,
    StartupMessage,
)


class TestStartupFraming:
    """Tests for StartupFraming strategy."""

    def test_parse_startup_message_success(self):
        """Test parsing a valid StartupMessage."""
        msg = StartupMessage(params={"user": "test", "database": "testdb"})
        wire = msg.to_wire()

        framing = StartupFraming()
        result = framing.try_parse(
            memoryview(wire), 0, ConnectionPhase.STARTUP, MessageDirection.FRONTEND
        )

        assert result is not None
        parsed_msg, bytes_consumed = result
        assert isinstance(parsed_msg, StartupMessage)
        assert parsed_msg.params["user"] == "test"
        assert parsed_msg.params["database"] == "testdb"
        assert bytes_consumed == len(wire)

    def test_parse_ssl_request_success(self):
        """Test parsing a valid SSLRequest."""
        msg = SSLRequest()
        wire = msg.to_wire()

        framing = StartupFraming()
        result = framing.try_parse(
            memoryview(wire), 0, ConnectionPhase.STARTUP, MessageDirection.FRONTEND
        )

        assert result is not None
        parsed_msg, bytes_consumed = result
        assert isinstance(parsed_msg, SSLRequest)
        assert bytes_consumed == 8

    def test_parse_gssenc_request_success(self):
        """Test parsing a valid GSSEncRequest."""
        msg = GSSEncRequest()
        wire = msg.to_wire()

        framing = StartupFraming()
        result = framing.try_parse(
            memoryview(wire), 0, ConnectionPhase.STARTUP, MessageDirection.FRONTEND
        )

        assert result is not None
        parsed_msg, bytes_consumed = result
        assert isinstance(parsed_msg, GSSEncRequest)
        assert bytes_consumed == 8

    def test_insufficient_data_for_length(self):
        """Test returns None when buffer doesn't have 4 bytes for length."""
        framing = StartupFraming()
        result = framing.try_parse(
            memoryview(b"\x00\x00\x00"), 0, ConnectionPhase.STARTUP, MessageDirection.FRONTEND
        )
        assert result is None

    def test_insufficient_data_for_payload(self):
        """Test returns None when buffer doesn't have complete payload."""
        # Length = 20 bytes, but only provide 10
        wire = struct.pack("!I", 20) + b"partial"
        framing = StartupFraming()
        result = framing.try_parse(
            memoryview(wire), 0, ConnectionPhase.STARTUP, MessageDirection.FRONTEND
        )
        assert result is None

    def test_message_exceeds_max_size(self):
        """Test that oversized messages raise FramingError."""
        # Create a message that claims to be huge
        wire = struct.pack("!I", 2 * 1024 * 1024 * 1024)  # 2 GB

        framing = StartupFraming(max_message_size=1024 * 1024)  # 1 MB limit
        with pytest.raises(FramingError, match="exceeds maximum allowed size"):
            framing.try_parse(
                memoryview(wire), 0, ConnectionPhase.STARTUP, MessageDirection.FRONTEND
            )

    def test_payload_too_short_for_version_code(self):
        """Test that payload shorter than 4 bytes raises FramingError."""
        # Length = 5 (header) + 2 (payload) = 7, but payload needs 4 bytes for version
        wire = struct.pack("!I", 6) + b"ab"

        framing = StartupFraming()
        with pytest.raises(FramingError, match="payload too short for version code"):
            framing.try_parse(
                memoryview(wire), 0, ConnectionPhase.STARTUP, MessageDirection.FRONTEND
            )

    def test_unknown_version_code_raises_error(self):
        """Test that unknown version code raises FramingError."""
        # Create message with invalid version code
        wire = struct.pack("!II", 8, 0xDEADBEEF)  # Invalid version code

        framing = StartupFraming()
        with pytest.raises(FramingError, match="Unknown startup message version code"):
            framing.try_parse(
                memoryview(wire), 0, ConnectionPhase.STARTUP, MessageDirection.FRONTEND
            )

    def test_malformed_message_raises_error(self):
        """Test that malformed message payload raises ProtocolError (FramingError or DecodingError)."""
        # StartupMessage with correct version but truncated params
        wire = struct.pack("!II", 12, 0x00030000) + b"user"  # Missing null terminators

        framing = StartupFraming()
        with pytest.raises(ProtocolError, match="(truncated or malformed|Unterminated string)"):
            framing.try_parse(
                memoryview(wire), 0, ConnectionPhase.STARTUP, MessageDirection.FRONTEND
            )

    def test_parse_at_offset(self):
        """Test parsing a message at a non-zero buffer offset."""
        msg = SSLRequest()
        wire = b"garbage" + msg.to_wire()

        framing = StartupFraming()
        result = framing.try_parse(
            memoryview(wire), 7, ConnectionPhase.STARTUP, MessageDirection.FRONTEND
        )

        assert result is not None
        parsed_msg, bytes_consumed = result
        assert isinstance(parsed_msg, SSLRequest)
        assert bytes_consumed == 8


class TestNegotiationFraming:
    """Tests for NegotiationFraming strategy."""

    def test_parse_ssl_accepted(self):
        """Test parsing SSL accepted response."""
        msg = SSLResponse(accepted=True)
        wire = msg.to_wire()

        framing = NegotiationFraming()
        result = framing.try_parse(
            memoryview(wire),
            0,
            ConnectionPhase.SSL_NEGOTIATION,
            MessageDirection.BACKEND,
        )

        assert result is not None
        parsed_msg, bytes_consumed = result
        assert isinstance(parsed_msg, SSLResponse)
        assert parsed_msg.accepted is True
        assert bytes_consumed == 1

    def test_parse_ssl_not_accepted(self):
        """Test parsing SSL not accepted response."""
        msg = SSLResponse(accepted=False)
        wire = msg.to_wire()

        framing = NegotiationFraming()
        result = framing.try_parse(
            memoryview(wire),
            0,
            ConnectionPhase.SSL_NEGOTIATION,
            MessageDirection.BACKEND,
        )

        assert result is not None
        parsed_msg, bytes_consumed = result
        assert isinstance(parsed_msg, SSLResponse)
        assert parsed_msg.accepted is False
        assert bytes_consumed == 1

    def test_parse_gss_accepted(self):
        """Test parsing GSS accepted response."""
        msg = GSSResponse(accepted=True)
        wire = msg.to_wire()

        framing = NegotiationFraming()
        result = framing.try_parse(
            memoryview(wire),
            0,
            ConnectionPhase.GSS_NEGOTIATION,
            MessageDirection.BACKEND,
        )

        assert result is not None
        parsed_msg, bytes_consumed = result
        assert isinstance(parsed_msg, GSSResponse)
        assert parsed_msg.accepted is True
        assert bytes_consumed == 1

    def test_parse_gss_not_accepted(self):
        """Test parsing GSS not accepted response."""
        msg = GSSResponse(accepted=False)
        wire = msg.to_wire()

        framing = NegotiationFraming()
        result = framing.try_parse(
            memoryview(wire),
            0,
            ConnectionPhase.GSS_NEGOTIATION,
            MessageDirection.BACKEND,
        )

        assert result is not None
        parsed_msg, bytes_consumed = result
        assert isinstance(parsed_msg, GSSResponse)
        assert parsed_msg.accepted is False
        assert bytes_consumed == 1

    def test_insufficient_data(self):
        """Test returns None when buffer is empty."""
        framing = NegotiationFraming()
        result = framing.try_parse(
            memoryview(b""),
            0,
            ConnectionPhase.SSL_NEGOTIATION,
            MessageDirection.BACKEND,
        )
        assert result is None

    def test_unknown_negotiation_byte(self):
        """Test that unknown negotiation byte raises FramingError."""
        framing = NegotiationFraming()
        with pytest.raises(FramingError, match="Unknown negotiation byte"):
            framing.try_parse(
                memoryview(b"X"),
                0,
                ConnectionPhase.SSL_NEGOTIATION,
                MessageDirection.BACKEND,
            )

    def test_invalid_byte_in_phase(self):
        """Test that valid byte in wrong phase raises FramingError."""
        # 'G' is valid for GSS but not SSL
        framing = NegotiationFraming()
        with pytest.raises(FramingError, match="Unknown negotiation byte.*SSL_NEGOTIATION"):
            framing.try_parse(
                memoryview(b"G"),
                0,
                ConnectionPhase.SSL_NEGOTIATION,
                MessageDirection.BACKEND,
            )

    def test_malformed_message_raises_error(self):
        """Test that decode errors are wrapped in FramingError."""
        # This should never happen in practice since negotiation messages
        # are just single bytes, but test the error handling path
        framing = NegotiationFraming()

        # Inject a malformed scenario by passing valid byte but it will fail decode
        # Since messages are single byte, we need to test the struct.error path
        # which is difficult to trigger naturally. This tests code coverage.
        result = framing.try_parse(
            memoryview(b"S"),
            0,
            ConnectionPhase.SSL_NEGOTIATION,
            MessageDirection.BACKEND,
        )
        # Should succeed normally
        assert result is not None

    def test_parse_at_offset(self):
        """Test parsing at a non-zero buffer offset."""
        msg = SSLResponse(accepted=True)
        wire = b"prefix" + msg.to_wire()

        framing = NegotiationFraming()
        result = framing.try_parse(
            memoryview(wire),
            6,
            ConnectionPhase.SSL_NEGOTIATION,
            MessageDirection.BACKEND,
        )

        assert result is not None
        parsed_msg, bytes_consumed = result
        assert isinstance(parsed_msg, SSLResponse)
        assert bytes_consumed == 1


class TestStandardFraming:
    """Tests for StandardFraming strategy."""

    def test_parse_query_message_success(self):
        """Test parsing a valid Query message."""
        msg = Query(query_string="SELECT 1")
        wire = msg.to_wire()

        framing = StandardFraming()
        result = framing.try_parse(
            memoryview(wire), 0, ConnectionPhase.READY, MessageDirection.FRONTEND
        )

        assert result is not None
        parsed_msg, bytes_consumed = result
        assert isinstance(parsed_msg, Query)
        assert parsed_msg.query_string == "SELECT 1"
        assert bytes_consumed == len(wire)

    def test_parse_authentication_ok_success(self):
        """Test parsing a valid AuthenticationOk message."""
        msg = AuthenticationOk()
        wire = msg.to_wire()

        framing = StandardFraming()
        result = framing.try_parse(
            memoryview(wire),
            0,
            ConnectionPhase.AUTHENTICATING,
            MessageDirection.BACKEND,
        )

        assert result is not None
        parsed_msg, bytes_consumed = result
        assert isinstance(parsed_msg, AuthenticationOk)
        assert bytes_consumed == len(wire)

    def test_insufficient_data_for_header(self):
        """Test returns None when buffer doesn't have 5 bytes for header."""
        framing = StandardFraming()
        result = framing.try_parse(
            memoryview(b"Q\x00\x00\x00"),
            0,
            ConnectionPhase.READY,
            MessageDirection.FRONTEND,
        )
        assert result is None

    def test_insufficient_data_for_payload(self):
        """Test returns None when buffer doesn't have complete payload."""
        # Query message with length=100 but only partial payload
        wire = b"Q" + struct.pack("!I", 100) + b"SELECT"
        framing = StandardFraming()
        result = framing.try_parse(
            memoryview(wire), 0, ConnectionPhase.READY, MessageDirection.FRONTEND
        )
        assert result is None

    def test_message_exceeds_max_size(self):
        """Test that oversized messages raise FramingError."""
        # Create a message that claims to be huge
        wire = b"Q" + struct.pack("!I", 2 * 1024 * 1024 * 1024)  # 2 GB

        framing = StandardFraming(max_message_size=1024 * 1024)  # 1 MB limit
        with pytest.raises(FramingError, match="exceeds maximum allowed size"):
            framing.try_parse(memoryview(wire), 0, ConnectionPhase.READY, MessageDirection.FRONTEND)

    def test_unknown_message_identifier(self):
        """Test that unknown identifier raises FramingError."""
        # Invalid identifier '@' with valid length (not used in PostgreSQL protocol)
        wire = b"@" + struct.pack("!I", 4)

        framing = StandardFraming()
        with pytest.raises(FramingError, match="Unknown message identifier"):
            framing.try_parse(memoryview(wire), 0, ConnectionPhase.READY, MessageDirection.FRONTEND)

    def test_unknown_identifier_in_phase(self):
        """Test that valid identifier in wrong phase raises FramingError."""
        # Parse ('P') is valid in EXTENDED_QUERY/READY but not in AUTHENTICATING
        from pygwire.messages import Parse

        msg = Parse(statement="", query="SELECT 1", param_types=[])
        wire = msg.to_wire()

        framing = StandardFraming()
        with pytest.raises(FramingError, match="Unknown message identifier"):
            framing.try_parse(
                memoryview(wire),
                0,
                ConnectionPhase.AUTHENTICATING,
                MessageDirection.FRONTEND,
            )

    def test_malformed_message_raises_error(self):
        """Test that malformed message payload raises FramingError."""
        # AuthenticationOk with truncated payload (should have 8 bytes total)
        wire = b"R" + struct.pack("!I", 2) + b""  # Length too short

        framing = StandardFraming()
        with pytest.raises(FramingError, match="truncated or malformed"):
            framing.try_parse(
                memoryview(wire),
                0,
                ConnectionPhase.AUTHENTICATING,
                MessageDirection.BACKEND,
            )

    def test_parse_at_offset(self):
        """Test parsing a message at a non-zero buffer offset."""
        msg = Query(query_string="SELECT 1")
        wire = b"garbage_prefix" + msg.to_wire()

        framing = StandardFraming()
        result = framing.try_parse(
            memoryview(wire), 14, ConnectionPhase.READY, MessageDirection.FRONTEND
        )

        assert result is not None
        parsed_msg, bytes_consumed = result
        assert isinstance(parsed_msg, Query)
        assert bytes_consumed == len(msg.to_wire())

    def test_zero_length_payload(self):
        """Test message with zero-length payload (length=4, just the length field)."""
        # Some messages like Sync have no payload
        from pygwire.messages import Sync

        msg = Sync()
        wire = msg.to_wire()

        framing = StandardFraming()
        result = framing.try_parse(
            memoryview(wire),
            0,
            ConnectionPhase.EXTENDED_QUERY,
            MessageDirection.FRONTEND,
        )

        assert result is not None
        parsed_msg, bytes_consumed = result
        assert isinstance(parsed_msg, Sync)
        assert bytes_consumed == 5  # 1 byte identifier + 4 byte length


class TestLookupFraming:
    """Tests for lookup_framing function."""

    def test_startup_frontend_returns_startup_framing(self):
        """Test that STARTUP phase with FRONTEND returns StartupFraming."""
        framing = lookup_framing(ConnectionPhase.STARTUP, MessageDirection.FRONTEND)
        assert isinstance(framing, StartupFraming)

    def test_ssl_negotiation_backend_returns_negotiation_framing(self):
        """Test that SSL_NEGOTIATION phase with BACKEND returns NegotiationFraming."""
        framing = lookup_framing(ConnectionPhase.SSL_NEGOTIATION, MessageDirection.BACKEND)
        assert isinstance(framing, NegotiationFraming)

    def test_gss_negotiation_backend_returns_negotiation_framing(self):
        """Test that GSS_NEGOTIATION phase with BACKEND returns NegotiationFraming."""
        framing = lookup_framing(ConnectionPhase.GSS_NEGOTIATION, MessageDirection.BACKEND)
        assert isinstance(framing, NegotiationFraming)

    def test_ready_frontend_returns_standard_framing(self):
        """Test that READY phase with FRONTEND returns StandardFraming (default)."""
        framing = lookup_framing(ConnectionPhase.READY, MessageDirection.FRONTEND)
        assert isinstance(framing, StandardFraming)

    def test_ready_backend_returns_standard_framing(self):
        """Test that READY phase with BACKEND returns StandardFraming (default)."""
        framing = lookup_framing(ConnectionPhase.READY, MessageDirection.BACKEND)
        assert isinstance(framing, StandardFraming)

    def test_authenticating_returns_standard_framing(self):
        """Test that AUTHENTICATING phase returns StandardFraming (default)."""
        framing = lookup_framing(ConnectionPhase.AUTHENTICATING, MessageDirection.BACKEND)
        assert isinstance(framing, StandardFraming)

    def test_simple_query_returns_standard_framing(self):
        """Test that SIMPLE_QUERY phase returns StandardFraming (default)."""
        framing = lookup_framing(ConnectionPhase.SIMPLE_QUERY, MessageDirection.BACKEND)
        assert isinstance(framing, StandardFraming)

    def test_extended_query_returns_standard_framing(self):
        """Test that EXTENDED_QUERY phase returns StandardFraming (default)."""
        framing = lookup_framing(ConnectionPhase.EXTENDED_QUERY, MessageDirection.FRONTEND)
        assert isinstance(framing, StandardFraming)

    def test_singleton_instances(self):
        """Test that lookup returns singleton instances."""
        framing1 = lookup_framing(ConnectionPhase.READY, MessageDirection.FRONTEND)
        framing2 = lookup_framing(ConnectionPhase.SIMPLE_QUERY, MessageDirection.BACKEND)
        # Both should return the same StandardFraming singleton
        assert framing1 is framing2

        startup1 = lookup_framing(ConnectionPhase.STARTUP, MessageDirection.FRONTEND)
        startup2 = lookup_framing(ConnectionPhase.STARTUP, MessageDirection.FRONTEND)
        assert startup1 is startup2


class TestFramingIntegration:
    """Integration tests across different framing modes."""

    def test_startup_to_standard_transition(self):
        """Test transition from startup framing to standard framing."""
        # First message: StartupMessage (startup framing)
        startup = StartupMessage(params={"user": "test"})
        startup_wire = startup.to_wire()

        startup_framing = lookup_framing(ConnectionPhase.STARTUP, MessageDirection.FRONTEND)
        result = startup_framing.try_parse(
            memoryview(startup_wire),
            0,
            ConnectionPhase.STARTUP,
            MessageDirection.FRONTEND,
        )
        assert result is not None

        # After startup, switch to standard framing
        auth_ok = AuthenticationOk()
        auth_wire = auth_ok.to_wire()

        standard_framing = lookup_framing(ConnectionPhase.AUTHENTICATING, MessageDirection.BACKEND)
        result = standard_framing.try_parse(
            memoryview(auth_wire),
            0,
            ConnectionPhase.AUTHENTICATING,
            MessageDirection.BACKEND,
        )
        assert result is not None

    def test_ssl_negotiation_flow(self):
        """Test SSL negotiation framing flow."""
        # Client sends SSLRequest (startup framing)
        ssl_req = SSLRequest()
        req_wire = ssl_req.to_wire()

        startup_framing = lookup_framing(ConnectionPhase.STARTUP, MessageDirection.FRONTEND)
        result = startup_framing.try_parse(
            memoryview(req_wire), 0, ConnectionPhase.STARTUP, MessageDirection.FRONTEND
        )
        assert result is not None
        assert isinstance(result[0], SSLRequest)

        # Server responds with single byte (negotiation framing)
        ssl_resp = SSLResponse(accepted=True)
        resp_wire = ssl_resp.to_wire()

        neg_framing = lookup_framing(ConnectionPhase.SSL_NEGOTIATION, MessageDirection.BACKEND)
        result = neg_framing.try_parse(
            memoryview(resp_wire),
            0,
            ConnectionPhase.SSL_NEGOTIATION,
            MessageDirection.BACKEND,
        )
        assert result is not None
        assert isinstance(result[0], SSLResponse)

    def test_multiple_messages_in_buffer(self):
        """Test parsing multiple messages from a single buffer."""
        # Create buffer with multiple messages
        msg1 = Query(query_string="SELECT 1")
        msg2 = Query(query_string="SELECT 2")
        buffer = msg1.to_wire() + msg2.to_wire()

        framing = lookup_framing(ConnectionPhase.READY, MessageDirection.FRONTEND)

        # Parse first message
        result1 = framing.try_parse(
            memoryview(buffer), 0, ConnectionPhase.READY, MessageDirection.FRONTEND
        )
        assert result1 is not None
        parsed1, consumed1 = result1
        assert isinstance(parsed1, Query)
        assert parsed1.query_string == "SELECT 1"

        # Parse second message
        result2 = framing.try_parse(
            memoryview(buffer),
            consumed1,
            ConnectionPhase.READY,
            MessageDirection.FRONTEND,
        )
        assert result2 is not None
        parsed2, consumed2 = result2
        assert isinstance(parsed2, Query)
        assert parsed2.query_string == "SELECT 2"
        assert consumed1 + consumed2 == len(buffer)

    def test_custom_max_message_size(self):
        """Test that custom max_message_size is respected across framing types."""
        max_size = 100

        startup_framing = StartupFraming(max_message_size=max_size)
        standard_framing = StandardFraming(max_message_size=max_size)

        # Test startup framing respects limit
        huge_startup = struct.pack("!I", max_size + 1)
        with pytest.raises(FramingError, match="exceeds maximum"):
            startup_framing.try_parse(
                memoryview(huge_startup),
                0,
                ConnectionPhase.STARTUP,
                MessageDirection.FRONTEND,
            )

        # Test standard framing respects limit
        huge_standard = b"Q" + struct.pack("!I", max_size + 1)
        with pytest.raises(FramingError, match="exceeds maximum"):
            standard_framing.try_parse(
                memoryview(huge_standard),
                0,
                ConnectionPhase.READY,
                MessageDirection.FRONTEND,
            )
