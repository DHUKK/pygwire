"""Tests for adversarial and malformed message payloads."""

import struct

import pytest

from pygwire.codec import _BackendStreamDecoder, _FrontendStreamDecoder
from pygwire.messages import (
    AuthenticationSASL,
    Bind,
    DataRow,
    ErrorResponse,
    FieldDescription,
    NotificationResponse,
    ProtocolError,
    RowDescription,
)
from pygwire.state_machine import ConnectionPhase


# Helper to create decoders for malformed payload testing.
# These tests need low-level decoder access since they craft invalid wire data.
def BackendMessageDecoder():
    c = _BackendStreamDecoder()
    c.phase = ConnectionPhase.READY
    return c


def FrontendMessageDecoder():
    c = _FrontendStreamDecoder()
    c.phase = ConnectionPhase.READY
    return c


class TestTruncatedPayloads:
    """Tests for truncated payloads that claim more data than provided."""

    def test_row_description_truncated_field_count(self):
        """Test RowDescription with field count but truncated field data."""
        # Header: 'T' + length
        # Body: Int16(field_count=5) but only provide 2 fields
        decoder = BackendMessageDecoder()

        # Create a valid RowDescription with 2 fields
        msg = RowDescription(
            fields=[
                FieldDescription(
                    name="col1",
                    table_oid=0,
                    column_attr=0,
                    type_oid=23,
                    type_size=4,
                    type_modifier=-1,
                    format_code=0,
                ),
                FieldDescription(
                    name="col2",
                    table_oid=0,
                    column_attr=0,
                    type_oid=25,
                    type_size=-1,
                    type_modifier=-1,
                    format_code=0,
                ),
            ]
        )

        # Get the valid wire format
        wire = msg.to_wire()

        # Now corrupt it: replace field count with 5 instead of 2
        # Wire format: 'T' + Int32(length) + Int16(field_count) + fields
        corrupted = wire[:1] + wire[1:5] + struct.pack("!H", 5) + wire[7:]

        # Feed the corrupted message and try to read
        # This should raise ProtocolError due to incomplete data or struct.unpack failure
        with pytest.raises(ProtocolError):
            decoder.feed(corrupted)
            next(decoder)

    def test_data_row_truncated_column_count(self):
        """Test DataRow claiming more columns than provided."""
        decoder = BackendMessageDecoder()

        # Valid DataRow with 2 columns
        msg = DataRow(columns=[b"value1", b"value2"])
        wire = msg.to_wire()

        # Corrupt: change column count from 2 to 10
        # Wire format: 'D' + Int32(length) + Int16(column_count) + columns
        corrupted = wire[:1] + wire[1:5] + struct.pack("!H", 10) + wire[7:]

        # Either feed or read should raise ProtocolError
        with pytest.raises(ProtocolError):
            decoder.feed(corrupted)
            next(decoder)

    def test_authentication_sasl_truncated_mechanisms(self):
        """Test AuthenticationSASL claiming mechanisms but providing truncated data."""
        decoder = BackendMessageDecoder()

        # Valid message with 2 mechanisms
        msg = AuthenticationSASL(mechanisms=["SCRAM-SHA-256", "SCRAM-SHA-256-PLUS"])
        wire = msg.to_wire()

        # Take only first half of the payload (truncate mechanism names)
        payload_start = 1 + 4  # identifier + length
        truncated = wire[:payload_start] + wire[payload_start : payload_start + 15]

        # Adjust length field to match truncated payload
        new_length = len(truncated) - 1
        truncated = truncated[:1] + struct.pack("!I", new_length) + truncated[5:]

        with pytest.raises(ProtocolError):
            decoder.feed(truncated)
            next(decoder)

    def test_bind_truncated_parameter_values(self):
        """Test Bind claiming parameter values but providing truncated data."""
        decoder = FrontendMessageDecoder()

        # Valid Bind with 3 parameters
        msg = Bind(
            portal="",
            statement="stmt1",
            param_values=[b"value1", b"value2", b"value3"],
        )
        wire = msg.to_wire()

        # Truncate to remove last parameter data
        truncated = wire[:-20]

        # Adjust length field
        new_length = len(truncated) - 1
        truncated = truncated[:1] + struct.pack("!I", new_length) + truncated[5:]

        with pytest.raises(ProtocolError):
            decoder.feed(truncated)
            next(decoder)

    def test_error_response_truncated_fields(self):
        """Test ErrorResponse with truncated field data."""
        decoder = BackendMessageDecoder()

        msg = ErrorResponse(
            fields={
                "S": "ERROR",
                "C": "42P01",
                "M": "relation does not exist",
                "D": "The table was not found in the schema",
            }
        )
        wire = msg.to_wire()

        # Truncate the message in the middle
        truncated = wire[: len(wire) // 2]

        # Adjust length field
        new_length = len(truncated) - 1
        truncated = truncated[:1] + struct.pack("!I", new_length) + truncated[5:]

        with pytest.raises(ProtocolError):
            decoder.feed(truncated)
            next(decoder)


class TestInvalidCountFields:
    """Tests for negative or zero-length count fields where unexpected."""

    def test_parameter_description_negative_count(self):
        """Test ParameterDescription with negative parameter count."""
        decoder = BackendMessageDecoder()

        # Manually craft a message with negative count
        # 't' + length + Int16(-1)
        payload = struct.pack("!h", -1)
        length = len(payload) + 4
        wire = b"t" + struct.pack("!I", length) + payload

        with pytest.raises(ProtocolError):
            decoder.feed(wire)
            next(decoder)

    def test_row_description_negative_field_count(self):
        """Test RowDescription with negative field count."""
        decoder = BackendMessageDecoder()

        # 'T' + length + Int16(-1)
        payload = struct.pack("!h", -1)
        length = len(payload) + 4
        wire = b"T" + struct.pack("!I", length) + payload

        with pytest.raises(ProtocolError):
            decoder.feed(wire)
            next(decoder)

    def test_data_row_negative_column_count(self):
        """Test DataRow with negative column count."""
        decoder = BackendMessageDecoder()

        # 'D' + length + Int16(-1)
        payload = struct.pack("!h", -1)
        length = len(payload) + 4
        wire = b"D" + struct.pack("!I", length) + payload

        with pytest.raises(ProtocolError):
            decoder.feed(wire)
            next(decoder)

    def test_copy_in_response_negative_column_count(self):
        """Test CopyInResponse with negative column count."""
        decoder = BackendMessageDecoder()

        # 'G' + length + Int8(0) + Int16(-1)
        payload = struct.pack("!Bh", 0, -1)
        length = len(payload) + 4
        wire = b"G" + struct.pack("!I", length) + payload

        with pytest.raises(ProtocolError):
            decoder.feed(wire)
            next(decoder)

    def test_function_call_negative_argument_count(self):
        """Test FunctionCall with negative argument count."""
        decoder = FrontendMessageDecoder()

        # 'F' + length + Int32(function_oid) + Int16(arg_format_count) + Int16(arg_count=-1)
        payload = struct.pack("!IHh", 123, 0, -1)
        length = len(payload) + 4
        wire = b"F" + struct.pack("!I", length) + payload

        with pytest.raises(ProtocolError):
            decoder.feed(wire)
            next(decoder)


class TestOversizedDeclaredLengths:
    """Tests for payloads with oversized declared lengths."""

    def test_authentication_md5_oversized_length(self):
        """Test AuthenticationMD5Password with oversized length field."""
        decoder = BackendMessageDecoder()

        # Craft message header claiming 1MB payload for a 4-byte salt
        # 'R' + Int32(1000000) + Int32(5) + 4 bytes salt
        payload = struct.pack("!I", 5) + b"\x01\x02\x03\x04"
        wire = b"R" + struct.pack("!I", 1000000) + payload

        # Feed header and part of payload
        decoder.feed(wire)

        # The decoder should wait for more data but not crash
        # We can't complete the message with this oversized claim
        try:
            next(decoder)
            raise AssertionError("Should not have parsed incomplete message")
        except StopIteration:
            # Expected - not enough data
            pass


class TestEmbeddedNulls:
    """Tests for embedded nulls in unexpected positions."""

    def test_error_response_embedded_null_in_field_value(self):
        """Test ErrorResponse with embedded null in field value."""
        decoder = BackendMessageDecoder()

        # ErrorResponse should handle embedded nulls in field values
        # The wire format uses field_type + cstring for each field
        # Let's manually craft one with an embedded null

        # 'E' + length + 'S' + "ERR\x00OR" + \x00 + \x00 (terminator)
        # This is malformed because cstring should terminate at first null

        payload = b"SERR\x00OR\x00\x00"  # Field 'S' with value containing embedded null
        length = len(payload) + 4
        wire = b"E" + struct.pack("!I", length) + payload

        decoder.feed(wire)

        # The decoder will read until first null, so "ERR" becomes the value
        msg = next(decoder)
        assert isinstance(msg, ErrorResponse)
        assert msg.fields["S"] == "ERR"  # Stops at embedded null

    def test_notification_channel_embedded_null(self):
        """Test NotificationResponse with embedded null in channel name."""
        decoder = BackendMessageDecoder()

        # 'A' + length + pid + "chan\x00nel" + \x00 + "payload" + \x00
        # The cstring will terminate at the embedded null

        process_id = struct.pack("!I", 1234)
        payload = process_id + b"chan\x00nel\x00payload\x00"
        length = len(payload) + 4
        wire = b"A" + struct.pack("!I", length) + payload

        decoder.feed(wire)

        msg = next(decoder)
        assert isinstance(msg, NotificationResponse)
        # Channel name stops at embedded null
        assert msg.channel == "chan"


class TestMinimumPayloadSize:
    """Tests for payloads shorter than minimum required size."""

    def test_data_row_empty_payload(self):
        """Test DataRow with completely empty payload."""
        decoder = BackendMessageDecoder()

        # 'D' + length(4) + empty payload
        wire = b"D" + struct.pack("!I", 4)

        with pytest.raises(ProtocolError):
            decoder.feed(wire)
            next(decoder)

    def test_row_description_empty_payload(self):
        """Test RowDescription with empty payload (missing field count)."""
        decoder = BackendMessageDecoder()

        # 'T' + length(4) + empty payload
        wire = b"T" + struct.pack("!I", 4)

        with pytest.raises(ProtocolError):
            decoder.feed(wire)
            next(decoder)

    def test_notification_response_too_short(self):
        """Test NotificationResponse missing required fields."""
        decoder = BackendMessageDecoder()

        # 'A' + length + only pid, no channel or payload
        payload = struct.pack("!I", 1234)
        length = len(payload) + 4
        wire = b"A" + struct.pack("!I", length) + payload

        with pytest.raises(ProtocolError):
            decoder.feed(wire)
            next(decoder)


class TestInvalidNullHandling:
    """Tests for NULL handling in various contexts."""

    def test_bind_null_parameter_with_invalid_length(self):
        """Test Bind with NULL parameter using non-negative-1 length."""
        decoder = FrontendMessageDecoder()

        # Manually craft Bind with parameter length = -2 (invalid NULL indicator)
        # Valid NULL is -1 (0xFFFFFFFF)

        # Portal name (empty), statement name (empty), formats, values
        portal = b"\x00"
        statement = b"\x00"
        param_formats = struct.pack("!H", 0)  # No formats specified
        param_count = struct.pack("!H", 1)  # 1 parameter
        param_length = struct.pack("!i", -2)  # Invalid NULL indicator
        result_formats = struct.pack("!H", 0)  # No result formats

        payload = portal + statement + param_formats + param_count + param_length + result_formats

        length = len(payload) + 4
        wire = b"B" + struct.pack("!I", length) + payload

        with pytest.raises(ProtocolError):
            decoder.feed(wire)
            next(decoder)

    def test_data_row_column_with_zero_length(self):
        """Test DataRow column with length=0 (empty bytes, not NULL)."""
        decoder = BackendMessageDecoder()

        # DataRow with one column of zero length
        # This is actually valid - represents empty bytes, not NULL
        # 'D' + length + Int16(1) + Int32(0)
        payload = struct.pack("!HI", 1, 0)
        length = len(payload) + 4
        wire = b"D" + struct.pack("!I", length) + payload

        decoder.feed(wire)

        msg = next(decoder)
        assert isinstance(msg, DataRow)
        assert msg.columns == [b""]  # Empty bytes, not None


class TestPartialMessages:
    """Tests for partially received messages."""

    def test_partial_header_feed(self):
        """Test feeding partial message header."""
        decoder = BackendMessageDecoder()

        # Send only identifier and 2 bytes of length
        wire = b"R\x00\x00"
        decoder.feed(wire)

        # Should not be able to parse yet (incomplete)
        try:
            next(decoder)
            raise AssertionError("Should not have parsed incomplete header")
        except StopIteration:
            pass  # Expected

        # Send rest of header + payload
        wire2 = b"\x00\x08" + struct.pack("!I", 0)  # AuthenticationOk
        decoder.feed(wire2)

        msg = next(decoder)
        assert msg is not None

    def test_partial_payload_feed(self):
        """Test feeding partial message payload."""
        decoder = BackendMessageDecoder()

        # Create a RowDescription and feed it in chunks
        msg = RowDescription(
            fields=[
                FieldDescription(
                    name="column1",
                    table_oid=0,
                    column_attr=0,
                    type_oid=23,
                    type_size=4,
                    type_modifier=-1,
                    format_code=0,
                ),
            ]
        )
        wire = msg.to_wire()

        # Feed first half
        mid = len(wire) // 2
        decoder.feed(wire[:mid])

        # Should not be able to parse yet (incomplete)
        try:
            next(decoder)
            raise AssertionError("Should not have parsed incomplete payload")
        except StopIteration:
            pass  # Expected

        # Feed second half
        decoder.feed(wire[mid:])

        result = next(decoder)
        assert isinstance(result, RowDescription)
