"""Integration tests for framing strategy transitions across protocol phases."""

import struct

import pytest

from pygwire.constants import ConnectionPhase, MessageDirection
from pygwire.exceptions import FramingError
from pygwire.framing import (
    StandardFraming,
    StartupFraming,
    lookup_framing,
)
from pygwire.messages import (
    AuthenticationOk,
    Query,
    SSLRequest,
    SSLResponse,
    StartupMessage,
)


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
