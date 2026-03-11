"""Unit tests for startup phase messages."""

import pytest

from pygwire.constants import ProtocolVersion
from pygwire.exceptions import DecodingError
from pygwire.messages import (
    CancelRequest,
    GSSEncRequest,
    SSLRequest,
    StartupMessage,
)


class TestStartupMessage:
    """Tests for StartupMessage encoding/decoding."""

    def test_encode_empty_params(self):
        """Test encoding StartupMessage with no parameters."""
        msg = StartupMessage(params={})
        wire = msg.encode()

        # Should contain version code + final null terminator
        assert len(wire) >= 5
        assert wire[:4] == ProtocolVersion.V3_0.to_bytes(4, "big")
        assert wire[-1:] == b"\x00"

    def test_encode_single_param(self):
        """Test encoding StartupMessage with one parameter."""
        msg = StartupMessage(params={"user": "testuser"})
        wire = msg.encode()

        assert b"user\x00testuser\x00\x00" in wire

    def test_encode_multiple_params(self):
        """Test encoding StartupMessage with multiple parameters."""
        msg = StartupMessage(
            params={
                "user": "testuser",
                "database": "testdb",
                "application_name": "myapp",
            }
        )
        wire = msg.encode()

        # Verify all keys and values are present
        assert b"user\x00testuser\x00" in wire
        assert b"database\x00testdb\x00" in wire
        assert b"application_name\x00myapp\x00" in wire

    def test_decode_empty_params(self):
        """Test decoding StartupMessage with no parameters."""
        msg = StartupMessage(params={})
        wire = msg.encode()

        decoded = StartupMessage.decode(memoryview(wire))
        assert decoded.params == {}

    def test_decode_single_param(self):
        """Test decoding StartupMessage with one parameter."""
        msg = StartupMessage(params={"user": "testuser"})
        wire = msg.encode()

        decoded = StartupMessage.decode(memoryview(wire))
        assert decoded.params == {"user": "testuser"}

    def test_decode_multiple_params(self):
        """Test decoding StartupMessage with multiple parameters."""
        params = {
            "user": "testuser",
            "database": "testdb",
            "application_name": "myapp",
            "client_encoding": "UTF8",
        }
        msg = StartupMessage(params=params)
        wire = msg.encode()

        decoded = StartupMessage.decode(memoryview(wire))
        assert decoded.params == params

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = StartupMessage(
            params={
                "user": "alice",
                "database": "production",
                "application_name": "web_app",
                "client_encoding": "UTF8",
                "DateStyle": "ISO, MDY",
            }
        )

        wire = original.encode()
        decoded = StartupMessage.decode(memoryview(wire))

        assert decoded.params == original.params
        assert decoded.protocol_version == ProtocolVersion.V3_0  # Default version

    def test_unicode_in_params(self):
        """Test encoding/decoding with Unicode characters."""
        msg = StartupMessage(params={"user": "用户", "database": "データベース"})

        wire = msg.encode()
        decoded = StartupMessage.decode(memoryview(wire))

        assert decoded.params["user"] == "用户"
        assert decoded.params["database"] == "データベース"

    def test_to_wire_includes_length(self):
        """Test that to_wire() includes length header."""
        msg = StartupMessage(params={"user": "test"})
        wire = msg.to_wire()

        # Should start with 4-byte length field
        length = int.from_bytes(wire[:4], "big")
        assert length == len(wire)  # Length field includes itself

    def test_empty_initialization(self):
        """Test StartupMessage can be created with no params arg."""
        msg = StartupMessage()
        assert msg.params == {}

    def test_params_initialization(self):
        """Test StartupMessage initialization with params."""
        params = {"user": "test"}
        msg = StartupMessage(params=params)
        assert msg.params == params

    def test_decode_unterminated_string_raises_error(self):
        """Test that unterminated string raises DecodingError."""
        # Create malformed payload: version + "user" without null terminator
        wire = ProtocolVersion.V3_0.to_bytes(4, "big") + b"user"

        with pytest.raises(DecodingError, match="Unterminated string"):
            StartupMessage.decode(memoryview(wire))

    def test_special_characters_in_params(self):
        """Test encoding/decoding with special characters."""
        msg = StartupMessage(
            params={
                "user": "test@example.com",
                "database": "my-database_2024",
                "options": "-c statement_timeout=5000",
            }
        )

        wire = msg.encode()
        decoded = StartupMessage.decode(memoryview(wire))

        assert decoded.params == msg.params

    def test_decode_v3_2_startup_message(self):
        """Test that v3.2 StartupMessage can be decoded."""
        # Create a v3.2 startup message manually (client would send this)
        params = {"user": "testuser", "database": "testdb"}
        buf = bytearray()
        buf.extend(ProtocolVersion.V3_2.to_bytes(4, "big"))
        for key, value in params.items():
            buf.extend(key.encode("utf-8"))
            buf.append(0)
            buf.extend(value.encode("utf-8"))
            buf.append(0)
        buf.append(0)  # final null terminator

        # Decode should work since StartupMessage is registered for both v3.0 and v3.2
        decoded = StartupMessage.decode(memoryview(buf))
        assert decoded.params == params
        assert decoded.protocol_version == ProtocolVersion.V3_2

    def test_encode_with_v3_2_protocol_version(self):
        """Test encoding StartupMessage with explicit v3.2 protocol version."""
        msg = StartupMessage(params={"user": "testuser"}, protocol_version=ProtocolVersion.V3_2)
        wire = msg.encode()

        # Should contain v3.2 version code
        assert wire[:4] == ProtocolVersion.V3_2.to_bytes(4, "big")
        assert b"user\x00testuser\x00\x00" in wire

    def test_encode_defaults_to_v3_0(self):
        """Test that encoding defaults to v3.0 when protocol_version not specified."""
        msg = StartupMessage(params={"user": "testuser"})
        wire = msg.encode()

        # Should contain v3.0 version code by default
        assert wire[:4] == ProtocolVersion.V3_0.to_bytes(4, "big")

    def test_v3_2_round_trip(self):
        """Test encode/decode round-trip with v3.2."""
        original = StartupMessage(
            params={"user": "alice", "database": "production"},
            protocol_version=ProtocolVersion.V3_2,
        )

        wire = original.encode()
        decoded = StartupMessage.decode(memoryview(wire))

        # Both params and protocol_version should be preserved
        assert decoded.params == original.params
        assert decoded.protocol_version == ProtocolVersion.V3_2


class TestSSLRequest:
    """Tests for SSLRequest encoding/decoding."""

    def test_encode(self):
        """Test encoding SSLRequest."""
        msg = SSLRequest()
        wire = msg.encode()

        # Should be exactly 4 bytes (the SSL request code)
        assert len(wire) == 4
        assert wire == ProtocolVersion.SSL_REQUEST.to_bytes(4, "big")

    def test_decode(self):
        """Test decoding SSLRequest."""
        wire = ProtocolVersion.SSL_REQUEST.to_bytes(4, "big")
        decoded = SSLRequest.decode(memoryview(wire))

        assert isinstance(decoded, SSLRequest)

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = SSLRequest()
        wire = original.encode()
        decoded = SSLRequest.decode(memoryview(wire))

        assert isinstance(decoded, SSLRequest)

    def test_to_wire_includes_length(self):
        """Test that to_wire() includes length header."""
        msg = SSLRequest()
        wire = msg.to_wire()

        # Should be 4 bytes length + 4 bytes code = 8 bytes
        assert len(wire) == 8
        length = int.from_bytes(wire[:4], "big")
        assert length == 8

    def test_multiple_instances_are_equal(self):
        """Test that SSLRequest instances encode identically."""
        msg1 = SSLRequest()
        msg2 = SSLRequest()

        assert msg1.encode() == msg2.encode()


class TestGSSEncRequest:
    """Tests for GSSEncRequest encoding/decoding."""

    def test_encode(self):
        """Test encoding GSSEncRequest."""
        msg = GSSEncRequest()
        wire = msg.encode()

        # Should be exactly 4 bytes (the GSSENC request code)
        assert len(wire) == 4
        assert wire == ProtocolVersion.GSSENC_REQUEST.to_bytes(4, "big")

    def test_decode(self):
        """Test decoding GSSEncRequest."""
        wire = ProtocolVersion.GSSENC_REQUEST.to_bytes(4, "big")
        decoded = GSSEncRequest.decode(memoryview(wire))

        assert isinstance(decoded, GSSEncRequest)

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = GSSEncRequest()
        wire = original.encode()
        decoded = GSSEncRequest.decode(memoryview(wire))

        assert isinstance(decoded, GSSEncRequest)

    def test_to_wire_includes_length(self):
        """Test that to_wire() includes length header."""
        msg = GSSEncRequest()
        wire = msg.to_wire()

        # Should be 4 bytes length + 4 bytes code = 8 bytes
        assert len(wire) == 8
        length = int.from_bytes(wire[:4], "big")
        assert length == 8

    def test_different_from_ssl_request(self):
        """Test that GSSEncRequest differs from SSLRequest."""
        ssl = SSLRequest()
        gss = GSSEncRequest()

        assert ssl.encode() != gss.encode()


class TestCancelRequest:
    """Tests for CancelRequest encoding/decoding."""

    def test_encode_v3_0(self):
        """Test encoding CancelRequest with 4-byte secret key (Protocol 3.0)."""
        msg = CancelRequest(process_id=12345, secret_key=b"\x01\x02\x03\x04")
        wire = msg.encode()

        # Should contain: cancel code (4) + process_id (4) + secret_key (4)
        assert len(wire) == 12
        assert wire[:4] == ProtocolVersion.CANCEL_REQUEST.to_bytes(4, "big")

    def test_encode_v3_2(self):
        """Test encoding CancelRequest with variable-length secret key (Protocol 3.2)."""
        long_key = b"a" * 32
        msg = CancelRequest(process_id=12345, secret_key=long_key)
        wire = msg.encode()

        # Should contain: cancel code (4) + process_id (4) + secret_key (32)
        assert len(wire) == 40
        assert wire[8:] == long_key

    def test_decode_v3_0(self):
        """Test decoding CancelRequest with 4-byte secret key."""
        msg = CancelRequest(process_id=12345, secret_key=b"\x01\x02\x03\x04")
        wire = msg.encode()

        decoded = CancelRequest.decode(memoryview(wire))
        assert decoded.process_id == 12345
        assert decoded.secret_key == b"\x01\x02\x03\x04"

    def test_decode_v3_2(self):
        """Test decoding CancelRequest with variable-length secret key."""
        long_key = b"secret_key_" * 5
        msg = CancelRequest(process_id=67890, secret_key=long_key)
        wire = msg.encode()

        decoded = CancelRequest.decode(memoryview(wire))
        assert decoded.process_id == 67890
        assert decoded.secret_key == long_key

    def test_round_trip_short_key(self):
        """Test encode/decode round-trip with short key."""
        original = CancelRequest(process_id=11111, secret_key=b"test")
        wire = original.encode()
        decoded = CancelRequest.decode(memoryview(wire))

        assert decoded.process_id == original.process_id
        assert decoded.secret_key == original.secret_key

    def test_round_trip_long_key(self):
        """Test encode/decode round-trip with long key."""
        long_key = b"x" * 256
        original = CancelRequest(process_id=99999, secret_key=long_key)
        wire = original.encode()
        decoded = CancelRequest.decode(memoryview(wire))

        assert decoded.process_id == original.process_id
        assert decoded.secret_key == original.secret_key

    def test_to_wire_includes_length(self):
        """Test that to_wire() includes length header."""
        msg = CancelRequest(process_id=12345, secret_key=b"test")
        wire = msg.to_wire()

        # Should start with 4-byte length field
        length = int.from_bytes(wire[:4], "big")
        assert length == len(wire)  # Length field includes itself

    def test_default_values(self):
        """Test CancelRequest with default values."""
        msg = CancelRequest()
        assert msg.process_id == 0
        assert msg.secret_key == b""

    def test_zero_process_id(self):
        """Test CancelRequest with process_id=0."""
        msg = CancelRequest(process_id=0, secret_key=b"key")
        wire = msg.encode()
        decoded = CancelRequest.decode(memoryview(wire))

        assert decoded.process_id == 0
        assert decoded.secret_key == b"key"

    def test_empty_secret_key(self):
        """Test CancelRequest with empty secret key."""
        msg = CancelRequest(process_id=12345, secret_key=b"")
        wire = msg.encode()
        decoded = CancelRequest.decode(memoryview(wire))

        assert decoded.process_id == 12345
        assert decoded.secret_key == b""

    def test_max_process_id(self):
        """Test CancelRequest with maximum process_id."""
        max_pid = 2**32 - 1  # Max unsigned 32-bit int
        msg = CancelRequest(process_id=max_pid, secret_key=b"test")
        wire = msg.encode()
        decoded = CancelRequest.decode(memoryview(wire))

        assert decoded.process_id == max_pid


class TestSpecialMessageIdentifiers:
    """Tests for special message identifier property."""

    def test_startup_message_has_no_identifier(self):
        """Test that StartupMessage has no identifier byte."""
        msg = StartupMessage(params={"user": "test"})
        assert msg.identifier == b""

    def test_ssl_request_has_no_identifier(self):
        """Test that SSLRequest has no identifier byte."""
        msg = SSLRequest()
        assert msg.identifier == b""

    def test_gssenc_request_has_no_identifier(self):
        """Test that GSSEncRequest has no identifier byte."""
        msg = GSSEncRequest()
        assert msg.identifier == b""

    def test_cancel_request_has_no_identifier(self):
        """Test that CancelRequest has no identifier byte."""
        msg = CancelRequest()
        assert msg.identifier == b""
