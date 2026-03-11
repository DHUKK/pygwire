"""Unit tests for authentication messages."""

import pytest

from pygwire.exceptions import ProtocolError
from pygwire.messages import (
    Authentication,
    AuthenticationCleartextPassword,
    AuthenticationGSS,
    AuthenticationGSSContinue,
    AuthenticationKerberosV5,
    AuthenticationMD5Password,
    AuthenticationOk,
    AuthenticationSASL,
    AuthenticationSASLContinue,
    AuthenticationSASLFinal,
    AuthenticationSSPI,
    GSSResponse,
    PasswordMessage,
    SASLInitialResponse,
    SASLResponse,
    SSLResponse,
)


class TestSSLResponse:
    """Tests for SSLResponse message."""

    def test_accepted_encode(self):
        """Test encoding accepted SSLResponse."""
        msg = SSLResponse(accepted=True)
        assert msg.encode() == b"S"

    def test_not_accepted_encode(self):
        """Test encoding not-accepted SSLResponse."""
        msg = SSLResponse(accepted=False)
        assert msg.encode() == b"N"

    def test_to_wire_is_single_byte(self):
        """Test to_wire returns single byte (no identifier or length prefix)."""
        assert SSLResponse(accepted=True).to_wire() == b"S"
        assert SSLResponse(accepted=False).to_wire() == b"N"

    def test_decode_supported(self):
        """Test decoding 'S' byte."""
        response = SSLResponse.decode(memoryview(b"S"))
        assert response.accepted is True

    def test_decode_not_supported(self):
        """Test decoding 'N' byte."""
        response = SSLResponse.decode(memoryview(b"N"))
        assert response.accepted is False

    def test_decode_invalid_raises_error(self):
        """Test decoding invalid byte raises ProtocolError."""
        with pytest.raises(ProtocolError, match="Unexpected SSL response byte"):
            SSLResponse.decode(memoryview(b"X"))


class TestGSSResponse:
    """Tests for GSSResponse message."""

    def test_accepted_encode(self):
        """Test encoding accepted GSSResponse."""
        msg = GSSResponse(accepted=True)
        assert msg.encode() == b"G"

    def test_not_accepted_encode(self):
        """Test encoding not-accepted GSSResponse."""
        msg = GSSResponse(accepted=False)
        assert msg.encode() == b"N"

    def test_to_wire_is_single_byte(self):
        """Test to_wire returns single byte (no identifier or length prefix)."""
        assert GSSResponse(accepted=True).to_wire() == b"G"
        assert GSSResponse(accepted=False).to_wire() == b"N"

    def test_decode_supported(self):
        """Test decoding 'G' byte."""
        response = GSSResponse.decode(memoryview(b"G"))
        assert response.accepted is True

    def test_decode_not_supported(self):
        """Test decoding 'N' byte."""
        response = GSSResponse.decode(memoryview(b"N"))
        assert response.accepted is False

    def test_decode_invalid_raises_error(self):
        """Test decoding invalid byte raises ProtocolError."""
        with pytest.raises(ProtocolError, match="Unexpected GSS response byte"):
            GSSResponse.decode(memoryview(b"X"))


class TestAuthenticationOk:
    """Tests for AuthenticationOk message."""

    def test_encode(self):
        """Test encoding AuthenticationOk."""
        msg = AuthenticationOk()
        wire = msg.encode()

        # Auth code 0 as Int32
        assert wire == b"\x00\x00\x00\x00"

    def test_decode(self):
        """Test decoding AuthenticationOk."""
        wire = b"\x00\x00\x00\x00"
        decoded = AuthenticationOk.decode(memoryview(wire))

        assert isinstance(decoded, AuthenticationOk)

    def test_decode_via_dispatcher(self):
        """Test decoding AuthenticationOk via Authentication dispatcher."""
        wire = b"\x00\x00\x00\x00"
        decoded = Authentication.decode(memoryview(wire))

        assert isinstance(decoded, AuthenticationOk)

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = AuthenticationOk()
        wire = original.encode()
        decoded = AuthenticationOk.decode(memoryview(wire))

        assert isinstance(decoded, AuthenticationOk)

    def test_auth_code(self):
        """Test auth_code class variable."""
        assert AuthenticationOk.auth_code == 0

    def test_identifier(self):
        """Test identifier is 'R'."""
        msg = AuthenticationOk()
        assert msg.identifier == b"R"


class TestAuthenticationKerberosV5:
    """Tests for AuthenticationKerberosV5 message."""

    def test_encode(self):
        """Test encoding AuthenticationKerberosV5."""
        msg = AuthenticationKerberosV5()
        wire = msg.encode()

        # Auth code 2 as Int32
        assert wire == b"\x00\x00\x00\x02"

    def test_decode(self):
        """Test decoding AuthenticationKerberosV5."""
        wire = b"\x00\x00\x00\x02"
        decoded = AuthenticationKerberosV5.decode(memoryview(wire))

        assert isinstance(decoded, AuthenticationKerberosV5)

    def test_decode_via_dispatcher(self):
        """Test decoding via Authentication dispatcher."""
        wire = b"\x00\x00\x00\x02"
        decoded = Authentication.decode(memoryview(wire))

        assert isinstance(decoded, AuthenticationKerberosV5)

    def test_auth_code(self):
        """Test auth_code class variable."""
        assert AuthenticationKerberosV5.auth_code == 2


class TestAuthenticationCleartextPassword:
    """Tests for AuthenticationCleartextPassword message."""

    def test_encode(self):
        """Test encoding AuthenticationCleartextPassword."""
        msg = AuthenticationCleartextPassword()
        wire = msg.encode()

        # Auth code 3 as Int32
        assert wire == b"\x00\x00\x00\x03"

    def test_decode(self):
        """Test decoding AuthenticationCleartextPassword."""
        wire = b"\x00\x00\x00\x03"
        decoded = AuthenticationCleartextPassword.decode(memoryview(wire))

        assert isinstance(decoded, AuthenticationCleartextPassword)

    def test_decode_via_dispatcher(self):
        """Test decoding via Authentication dispatcher."""
        wire = b"\x00\x00\x00\x03"
        decoded = Authentication.decode(memoryview(wire))

        assert isinstance(decoded, AuthenticationCleartextPassword)

    def test_auth_code(self):
        """Test auth_code class variable."""
        assert AuthenticationCleartextPassword.auth_code == 3


class TestAuthenticationMD5Password:
    """Tests for AuthenticationMD5Password message."""

    def test_encode_default_salt(self):
        """Test encoding with default salt."""
        msg = AuthenticationMD5Password()
        wire = msg.encode()

        # Auth code 5 + 4-byte salt
        assert wire[:4] == b"\x00\x00\x00\x05"
        assert wire[4:] == b"\x00\x00\x00\x00"

    def test_encode_custom_salt(self):
        """Test encoding with custom salt."""
        salt = b"\x01\x02\x03\x04"
        msg = AuthenticationMD5Password(salt=salt)
        wire = msg.encode()

        assert wire[:4] == b"\x00\x00\x00\x05"
        assert wire[4:] == salt

    def test_decode(self):
        """Test decoding AuthenticationMD5Password."""
        wire = b"\x00\x00\x00\x05\xaa\xbb\xcc\xdd"
        decoded = AuthenticationMD5Password.decode(memoryview(wire))

        assert decoded.salt == b"\xaa\xbb\xcc\xdd"

    def test_decode_via_dispatcher(self):
        """Test decoding via Authentication dispatcher."""
        wire = b"\x00\x00\x00\x05\x11\x22\x33\x44"
        decoded = Authentication.decode(memoryview(wire))

        assert isinstance(decoded, AuthenticationMD5Password)
        assert decoded.salt == b"\x11\x22\x33\x44"

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = AuthenticationMD5Password(salt=b"\xde\xad\xbe\xef")
        wire = original.encode()
        decoded = AuthenticationMD5Password.decode(memoryview(wire))

        assert decoded.salt == original.salt

    def test_auth_code(self):
        """Test auth_code class variable."""
        assert AuthenticationMD5Password.auth_code == 5


class TestAuthenticationGSS:
    """Tests for AuthenticationGSS message."""

    def test_encode(self):
        """Test encoding AuthenticationGSS."""
        msg = AuthenticationGSS()
        wire = msg.encode()

        assert wire == b"\x00\x00\x00\x07"

    def test_decode_via_dispatcher(self):
        """Test decoding via Authentication dispatcher."""
        wire = b"\x00\x00\x00\x07"
        decoded = Authentication.decode(memoryview(wire))

        assert isinstance(decoded, AuthenticationGSS)

    def test_auth_code(self):
        """Test auth_code class variable."""
        assert AuthenticationGSS.auth_code == 7


class TestAuthenticationGSSContinue:
    """Tests for AuthenticationGSSContinue message."""

    def test_encode_empty_data(self):
        """Test encoding with empty data."""
        msg = AuthenticationGSSContinue()
        wire = msg.encode()

        assert wire == b"\x00\x00\x00\x08"

    def test_encode_with_data(self):
        """Test encoding with GSS data."""
        data = b"gss_token_data"
        msg = AuthenticationGSSContinue(data=data)
        wire = msg.encode()

        assert wire[:4] == b"\x00\x00\x00\x08"
        assert wire[4:] == data

    def test_decode(self):
        """Test decoding AuthenticationGSSContinue."""
        wire = b"\x00\x00\x00\x08test_data"
        decoded = AuthenticationGSSContinue.decode(memoryview(wire))

        assert decoded.data == b"test_data"

    def test_decode_via_dispatcher(self):
        """Test decoding via Authentication dispatcher."""
        wire = b"\x00\x00\x00\x08binary_gss_data"
        decoded = Authentication.decode(memoryview(wire))

        assert isinstance(decoded, AuthenticationGSSContinue)
        assert decoded.data == b"binary_gss_data"

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = AuthenticationGSSContinue(data=b"gss_token_12345")
        wire = original.encode()
        decoded = AuthenticationGSSContinue.decode(memoryview(wire))

        assert decoded.data == original.data

    def test_auth_code(self):
        """Test auth_code class variable."""
        assert AuthenticationGSSContinue.auth_code == 8


class TestAuthenticationSSPI:
    """Tests for AuthenticationSSPI message."""

    def test_encode(self):
        """Test encoding AuthenticationSSPI."""
        msg = AuthenticationSSPI()
        wire = msg.encode()

        assert wire == b"\x00\x00\x00\x09"

    def test_decode_via_dispatcher(self):
        """Test decoding via Authentication dispatcher."""
        wire = b"\x00\x00\x00\x09"
        decoded = Authentication.decode(memoryview(wire))

        assert isinstance(decoded, AuthenticationSSPI)

    def test_auth_code(self):
        """Test auth_code class variable."""
        assert AuthenticationSSPI.auth_code == 9


class TestAuthenticationSASL:
    """Tests for AuthenticationSASL message."""

    def test_encode_empty_mechanisms(self):
        """Test encoding with no mechanisms."""
        msg = AuthenticationSASL()
        wire = msg.encode()

        # Auth code + final null terminator
        assert wire == b"\x00\x00\x00\x0a\x00"

    def test_encode_single_mechanism(self):
        """Test encoding with one mechanism."""
        msg = AuthenticationSASL(mechanisms=["SCRAM-SHA-256"])
        wire = msg.encode()

        assert wire[:4] == b"\x00\x00\x00\x0a"
        assert b"SCRAM-SHA-256\x00" in wire

    def test_encode_multiple_mechanisms(self):
        """Test encoding with multiple mechanisms."""
        msg = AuthenticationSASL(mechanisms=["SCRAM-SHA-256", "SCRAM-SHA-256-PLUS"])
        wire = msg.encode()

        assert b"SCRAM-SHA-256\x00" in wire
        assert b"SCRAM-SHA-256-PLUS\x00" in wire

    def test_decode_empty_mechanisms(self):
        """Test decoding with no mechanisms."""
        wire = b"\x00\x00\x00\x0a\x00"
        decoded = AuthenticationSASL.decode(memoryview(wire))

        assert decoded.mechanisms == []

    def test_decode_single_mechanism(self):
        """Test decoding with one mechanism."""
        wire = b"\x00\x00\x00\x0aSCRAM-SHA-256\x00\x00"
        decoded = AuthenticationSASL.decode(memoryview(wire))

        assert decoded.mechanisms == ["SCRAM-SHA-256"]

    def test_decode_multiple_mechanisms(self):
        """Test decoding with multiple mechanisms."""
        wire = b"\x00\x00\x00\x0aSCRAM-SHA-256\x00SCRAM-SHA-256-PLUS\x00\x00"
        decoded = AuthenticationSASL.decode(memoryview(wire))

        assert decoded.mechanisms == ["SCRAM-SHA-256", "SCRAM-SHA-256-PLUS"]

    def test_decode_via_dispatcher(self):
        """Test decoding via Authentication dispatcher."""
        wire = b"\x00\x00\x00\x0aSCRAM-SHA-256\x00\x00"
        decoded = Authentication.decode(memoryview(wire))

        assert isinstance(decoded, AuthenticationSASL)
        assert decoded.mechanisms == ["SCRAM-SHA-256"]

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = AuthenticationSASL(mechanisms=["SCRAM-SHA-256", "PLAIN"])
        wire = original.encode()
        decoded = AuthenticationSASL.decode(memoryview(wire))

        assert decoded.mechanisms == original.mechanisms

    def test_auth_code(self):
        """Test auth_code class variable."""
        assert AuthenticationSASL.auth_code == 10


class TestAuthenticationSASLContinue:
    """Tests for AuthenticationSASLContinue message."""

    def test_encode_empty_data(self):
        """Test encoding with empty data."""
        msg = AuthenticationSASLContinue()
        wire = msg.encode()

        assert wire == b"\x00\x00\x00\x0b"

    def test_encode_with_data(self):
        """Test encoding with SASL data."""
        data = b"r=server-nonce,s=salt,i=4096"
        msg = AuthenticationSASLContinue(data=data)
        wire = msg.encode()

        assert wire[:4] == b"\x00\x00\x00\x0b"
        assert wire[4:] == data

    def test_decode(self):
        """Test decoding AuthenticationSASLContinue."""
        wire = b"\x00\x00\x00\x0bsasl_server_data"
        decoded = AuthenticationSASLContinue.decode(memoryview(wire))

        assert decoded.data == b"sasl_server_data"

    def test_decode_via_dispatcher(self):
        """Test decoding via Authentication dispatcher."""
        wire = b"\x00\x00\x00\x0bserver_first_message"
        decoded = Authentication.decode(memoryview(wire))

        assert isinstance(decoded, AuthenticationSASLContinue)
        assert decoded.data == b"server_first_message"

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = AuthenticationSASLContinue(data=b"sasl_data_12345")
        wire = original.encode()
        decoded = AuthenticationSASLContinue.decode(memoryview(wire))

        assert decoded.data == original.data

    def test_auth_code(self):
        """Test auth_code class variable."""
        assert AuthenticationSASLContinue.auth_code == 11


class TestAuthenticationSASLFinal:
    """Tests for AuthenticationSASLFinal message."""

    def test_encode_empty_data(self):
        """Test encoding with empty data."""
        msg = AuthenticationSASLFinal()
        wire = msg.encode()

        assert wire == b"\x00\x00\x00\x0c"

    def test_encode_with_data(self):
        """Test encoding with SASL final data."""
        data = b"v=server-signature"
        msg = AuthenticationSASLFinal(data=data)
        wire = msg.encode()

        assert wire[:4] == b"\x00\x00\x00\x0c"
        assert wire[4:] == data

    def test_decode(self):
        """Test decoding AuthenticationSASLFinal."""
        wire = b"\x00\x00\x00\x0csasl_final_data"
        decoded = AuthenticationSASLFinal.decode(memoryview(wire))

        assert decoded.data == b"sasl_final_data"

    def test_decode_via_dispatcher(self):
        """Test decoding via Authentication dispatcher."""
        wire = b"\x00\x00\x00\x0cserver_final_message"
        decoded = Authentication.decode(memoryview(wire))

        assert isinstance(decoded, AuthenticationSASLFinal)
        assert decoded.data == b"server_final_message"

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = AuthenticationSASLFinal(data=b"v=signature_data")
        wire = original.encode()
        decoded = AuthenticationSASLFinal.decode(memoryview(wire))

        assert decoded.data == original.data

    def test_auth_code(self):
        """Test auth_code class variable."""
        assert AuthenticationSASLFinal.auth_code == 12


class TestAuthenticationDispatcher:
    """Tests for Authentication message dispatcher."""

    def test_unknown_auth_code_raises_error(self):
        """Test that unknown auth code raises ProtocolError."""
        wire = b"\x00\x00\x99\x99"  # Unknown auth code
        with pytest.raises(ProtocolError, match="Unknown authentication code"):
            Authentication.decode(memoryview(wire))

    def test_dispatcher_routes_to_correct_subclass(self):
        """Test dispatcher correctly routes to each subclass."""
        test_cases = [
            (b"\x00\x00\x00\x00", AuthenticationOk),
            (b"\x00\x00\x00\x03", AuthenticationCleartextPassword),
            (b"\x00\x00\x00\x05\x00\x00\x00\x00", AuthenticationMD5Password),
            (b"\x00\x00\x00\x0a\x00", AuthenticationSASL),
        ]

        for wire, expected_type in test_cases:
            decoded = Authentication.decode(memoryview(wire))
            assert isinstance(decoded, expected_type)


class TestPasswordMessage:
    """Tests for PasswordMessage (frontend)."""

    def test_encode_cleartext_password(self):
        """Test encoding cleartext password."""
        msg = PasswordMessage(password="secret123")
        wire = msg.encode()

        assert wire == b"secret123\x00"

    def test_encode_empty_password(self):
        """Test encoding empty password."""
        msg = PasswordMessage(password="")
        wire = msg.encode()

        assert wire == b"\x00"

    def test_encode_binary_data(self):
        """Test encoding binary data (SASL/GSSAPI)."""
        data = b"\x01\x02\x03\x04"
        msg = PasswordMessage(password=data)
        wire = msg.encode()

        # Binary data is returned as-is (no null terminator)
        assert wire == data

    def test_decode_cleartext_password(self):
        """Test decoding cleartext password."""
        wire = b"mypassword\x00"
        decoded = PasswordMessage.decode(memoryview(wire))

        assert decoded.password == "mypassword"

    def test_decode_binary_data(self):
        """Test decoding binary data without null terminator."""
        wire = b"\x01\x02\x03\x04\x05"
        decoded = PasswordMessage.decode(memoryview(wire))

        # Should be stored as bytes
        assert decoded.password == b"\x01\x02\x03\x04\x05"
        assert isinstance(decoded.password, bytes)

    def test_round_trip_cleartext(self):
        """Test encode/decode round-trip with cleartext."""
        original = PasswordMessage(password="test_password")
        wire = original.encode()
        decoded = PasswordMessage.decode(memoryview(wire))

        assert decoded.password == original.password

    def test_round_trip_binary(self):
        """Test encode/decode round-trip with binary data (no embedded nulls)."""
        original = PasswordMessage(password=b"binary_data_without_nulls")
        wire = original.encode()
        decoded = PasswordMessage.decode(memoryview(wire))

        assert decoded.password == original.password

    def test_identifier(self):
        """Test PasswordMessage has correct identifier."""
        msg = PasswordMessage(password="test")
        assert msg.identifier == b"p"

    def test_md5_password_format(self):
        """Test encoding MD5-hashed password."""
        # MD5 hash format: "md5" + md5(password + username)
        hashed = "md5" + "a" * 32  # Simulated MD5 hash
        msg = PasswordMessage(password=hashed)
        wire = msg.encode()

        assert wire == (hashed.encode() + b"\x00")

    def test_default_password(self):
        """Test PasswordMessage default initialization."""
        msg = PasswordMessage()
        assert msg.password == ""


class TestSASLInitialResponse:
    """Tests for SASLInitialResponse (frontend)."""

    def test_encode_with_data(self):
        """Test encoding SASL initial response with data."""
        msg = SASLInitialResponse(mechanism="SCRAM-SHA-256", data=b"client-first")
        wire = msg.encode()

        assert b"SCRAM-SHA-256\x00" in wire
        assert b"client-first" in wire

    def test_encode_without_data(self):
        """Test encoding SASL initial response without data."""
        msg = SASLInitialResponse(mechanism="SCRAM-SHA-256", data=b"")
        wire = msg.encode()

        assert b"SCRAM-SHA-256\x00" in wire
        # Should have -1 for data length
        assert b"\xff\xff\xff\xff" in wire

    def test_decode_with_data(self):
        """Test decoding SASL initial response with data."""
        msg = SASLInitialResponse(mechanism="SCRAM-SHA-256", data=b"n,,n=user,r=nonce")
        wire = msg.encode()

        decoded = SASLInitialResponse.decode(memoryview(wire))
        assert decoded.mechanism == "SCRAM-SHA-256"
        assert decoded.data == b"n,,n=user,r=nonce"

    def test_decode_without_data(self):
        """Test decoding SASL initial response without data."""
        msg = SASLInitialResponse(mechanism="PLAIN", data=b"")
        wire = msg.encode()

        decoded = SASLInitialResponse.decode(memoryview(wire))
        assert decoded.mechanism == "PLAIN"
        assert decoded.data == b""

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = SASLInitialResponse(mechanism="SCRAM-SHA-256", data=b"client_data")
        wire = original.encode()
        decoded = SASLInitialResponse.decode(memoryview(wire))

        assert decoded.mechanism == original.mechanism
        assert decoded.data == original.data

    def test_to_wire_uses_password_identifier(self):
        """Test that to_wire() uses 'p' identifier."""
        msg = SASLInitialResponse(mechanism="SCRAM-SHA-256", data=b"test")
        wire = msg.to_wire()

        # Should start with 'p' identifier
        assert wire[0:1] == b"p"

    def test_default_values(self):
        """Test SASLInitialResponse default initialization."""
        msg = SASLInitialResponse()
        assert msg.mechanism == ""
        assert msg.data == b""


class TestSASLResponse:
    """Tests for SASLResponse (frontend)."""

    def test_encode(self):
        """Test encoding SASL response."""
        data = b"c=biws,r=nonce,p=proof"
        msg = SASLResponse(data=data)
        wire = msg.encode()

        assert wire == data

    def test_decode(self):
        """Test decoding SASL response."""
        data = b"client_final_message"
        decoded = SASLResponse.decode(memoryview(data))

        assert decoded.data == data

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = SASLResponse(data=b"sasl_response_data_12345")
        wire = original.encode()
        decoded = SASLResponse.decode(memoryview(wire))

        assert decoded.data == original.data

    def test_to_wire_uses_password_identifier(self):
        """Test that to_wire() uses 'p' identifier."""
        msg = SASLResponse(data=b"test")
        wire = msg.to_wire()

        # Should start with 'p' identifier
        assert wire[0:1] == b"p"

    def test_default_data(self):
        """Test SASLResponse default initialization."""
        msg = SASLResponse()
        assert msg.data == b""

    def test_empty_data(self):
        """Test SASLResponse with empty data."""
        msg = SASLResponse(data=b"")
        wire = msg.encode()
        decoded = SASLResponse.decode(memoryview(wire))

        assert decoded.data == b""
