"""Unit tests for extended query, copy, error, notification, and misc messages."""

from pygwire.messages import (
    # Misc
    BackendKeyData,
    Bind,
    BindComplete,
    Close,
    CloseComplete,
    CopyBothResponse,
    # COPY protocol
    CopyData,
    CopyDone,
    CopyFail,
    CopyInResponse,
    CopyOutResponse,
    Describe,
    # Errors and notifications
    ErrorResponse,
    Execute,
    Flush,
    FunctionCall,
    FunctionCallResponse,
    NegotiateProtocolVersion,
    NoData,
    NoticeResponse,
    NotificationResponse,
    ParameterDescription,
    ParameterStatus,
    # Extended query
    Parse,
    ParseComplete,
    PortalSuspended,
    Sync,
    Terminate,
)


class TestParse:
    """Tests for Parse message (extended query)."""

    def test_encode_minimal(self):
        """Test encoding Parse with minimal fields."""
        msg = Parse(statement="", query="SELECT 1")
        wire = msg.encode()

        assert b"\x00" in wire  # Empty statement name
        assert b"SELECT 1\x00" in wire

    def test_encode_with_statement_name(self):
        """Test encoding Parse with statement name."""
        msg = Parse(statement="stmt1", query="SELECT $1", param_types=[23])
        wire = msg.encode()

        assert b"stmt1\x00" in wire
        assert b"SELECT $1\x00" in wire

    def test_decode(self):
        """Test decoding Parse."""
        msg = Parse(statement="stmt1", query="SELECT $1, $2", param_types=[23, 25])
        wire = msg.encode()
        decoded = Parse.decode(memoryview(wire))

        assert decoded.statement == "stmt1"
        assert decoded.query == "SELECT $1, $2"
        assert decoded.param_types == [23, 25]

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = Parse(
            statement="test",
            query="SELECT * FROM users WHERE id = $1",
            param_types=[23],
        )
        wire = original.encode()
        decoded = Parse.decode(memoryview(wire))

        assert decoded.statement == original.statement
        assert decoded.query == original.query
        assert decoded.param_types == original.param_types


class TestBind:
    """Tests for Bind message (extended query)."""

    def test_encode_minimal(self):
        """Test encoding Bind with minimal fields."""
        msg = Bind(portal="", statement="", param_values=[])
        wire = msg.encode()

        assert len(wire) > 0

    def test_encode_with_values(self):
        """Test encoding Bind with parameter values."""
        msg = Bind(
            portal="",
            statement="stmt1",
            param_formats=[0],
            param_values=[b"42"],
            result_formats=[0],
        )
        wire = msg.encode()

        assert b"stmt1\x00" in wire

    def test_encode_with_null(self):
        """Test encoding Bind with NULL parameter."""
        msg = Bind(portal="", statement="", param_values=[None])
        wire = msg.encode()

        # Should contain -1 for NULL
        assert b"\xff\xff\xff\xff" in wire

    def test_decode(self):
        """Test decoding Bind."""
        msg = Bind(
            portal="portal1",
            statement="stmt1",
            param_formats=[0, 0],
            param_values=[b"value1", b"value2"],
            result_formats=[0],
        )
        wire = msg.encode()
        decoded = Bind.decode(memoryview(wire))

        assert decoded.portal == "portal1"
        assert decoded.statement == "stmt1"
        assert decoded.param_values == [b"value1", b"value2"]

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = Bind(portal="", statement="stmt", param_values=[b"test", None, b"data"])
        wire = original.encode()
        decoded = Bind.decode(memoryview(wire))

        assert decoded.portal == original.portal
        assert decoded.statement == original.statement
        assert decoded.param_values == original.param_values

    def test_round_trip_with_formats(self):
        """Test encode/decode round-trip verifying param_formats and result_formats."""
        original = Bind(
            portal="my_portal",
            statement="my_stmt",
            param_formats=[1, 0, 1],  # binary, text, binary
            param_values=[b"\x00\x01", b"text", b"\xff\xfe"],
            result_formats=[1, 1, 0],  # binary, binary, text
        )
        wire = original.encode()
        decoded = Bind.decode(memoryview(wire))

        assert decoded.portal == original.portal
        assert decoded.statement == original.statement
        assert decoded.param_formats == original.param_formats
        assert decoded.param_values == original.param_values
        assert decoded.result_formats == original.result_formats

    def test_round_trip_all_formats_default(self):
        """Test Bind with default format codes (all text)."""
        original = Bind(
            portal="portal1",
            statement="stmt1",
            param_formats=[],  # Empty means all text
            param_values=[b"val1", b"val2"],
            result_formats=[],  # Empty means all text
        )
        wire = original.encode()
        decoded = Bind.decode(memoryview(wire))

        assert decoded.portal == original.portal
        assert decoded.statement == original.statement
        assert decoded.param_formats == original.param_formats
        assert decoded.param_values == original.param_values
        assert decoded.result_formats == original.result_formats

    def test_round_trip_with_null_parameters(self):
        """Test Bind with multiple NULL parameters."""
        original = Bind(
            portal="",
            statement="test",
            param_values=[None, b"data", None, None, b"more"],
        )
        wire = original.encode()
        decoded = Bind.decode(memoryview(wire))

        assert decoded.param_values == original.param_values
        assert decoded.param_values[0] is None
        assert decoded.param_values[2] is None
        assert decoded.param_values[3] is None


class TestDescribe:
    """Tests for Describe message."""

    def test_encode_statement(self):
        """Test encoding Describe for statement."""
        msg = Describe(kind="S", name="stmt1")
        wire = msg.encode()

        assert wire == b"Sstmt1\x00"

    def test_encode_portal(self):
        """Test encoding Describe for portal."""
        msg = Describe(kind="P", name="portal1")
        wire = msg.encode()

        assert wire == b"Pportal1\x00"

    def test_decode(self):
        """Test decoding Describe."""
        wire = b"Stest_statement\x00"
        decoded = Describe.decode(memoryview(wire))

        assert decoded.kind == "S"
        assert decoded.name == "test_statement"

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = Describe(kind="P", name="my_portal")
        wire = original.encode()
        decoded = Describe.decode(memoryview(wire))

        assert decoded.kind == original.kind
        assert decoded.name == original.name


class TestExecute:
    """Tests for Execute message."""

    def test_encode_unlimited_rows(self):
        """Test encoding Execute with max_rows=0 (unlimited)."""
        msg = Execute(portal="", max_rows=0)
        wire = msg.encode()

        assert b"\x00" in wire  # Empty portal name
        assert b"\x00\x00\x00\x00" in wire  # max_rows=0

    def test_encode_limited_rows(self):
        """Test encoding Execute with limited rows."""
        msg = Execute(portal="portal1", max_rows=100)
        wire = msg.encode()

        assert b"portal1\x00" in wire

    def test_decode(self):
        """Test decoding Execute."""
        msg = Execute(portal="test", max_rows=50)
        wire = msg.encode()
        decoded = Execute.decode(memoryview(wire))

        assert decoded.portal == "test"
        assert decoded.max_rows == 50

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = Execute(portal="my_portal", max_rows=1000)
        wire = original.encode()
        decoded = Execute.decode(memoryview(wire))

        assert decoded.portal == original.portal
        assert decoded.max_rows == original.max_rows


class TestClose:
    """Tests for Close message."""

    def test_encode_statement(self):
        """Test encoding Close for statement."""
        msg = Close(kind="S", name="stmt1")
        wire = msg.encode()

        assert wire == b"Sstmt1\x00"

    def test_encode_portal(self):
        """Test encoding Close for portal."""
        msg = Close(kind="P", name="portal1")
        wire = msg.encode()

        assert wire == b"Pportal1\x00"

    def test_decode(self):
        """Test decoding Close."""
        wire = b"Smy_statement\x00"
        decoded = Close.decode(memoryview(wire))

        assert decoded.kind == "S"
        assert decoded.name == "my_statement"

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = Close(kind="P", name="temp_portal")
        wire = original.encode()
        decoded = Close.decode(memoryview(wire))

        assert decoded.kind == original.kind
        assert decoded.name == original.name


class TestExtendedQueryCompletionMessages:
    """Tests for extended query completion messages."""

    def test_parse_complete(self):
        """Test ParseComplete message."""
        msg = ParseComplete()
        wire = msg.encode()
        decoded = ParseComplete.decode(memoryview(wire))

        assert isinstance(decoded, ParseComplete)
        assert wire == b""

    def test_bind_complete(self):
        """Test BindComplete message."""
        msg = BindComplete()
        wire = msg.encode()
        decoded = BindComplete.decode(memoryview(wire))

        assert isinstance(decoded, BindComplete)
        assert wire == b""

    def test_close_complete(self):
        """Test CloseComplete message."""
        msg = CloseComplete()
        wire = msg.encode()
        decoded = CloseComplete.decode(memoryview(wire))

        assert isinstance(decoded, CloseComplete)
        assert wire == b""

    def test_no_data(self):
        """Test NoData message."""
        msg = NoData()
        wire = msg.encode()
        decoded = NoData.decode(memoryview(wire))

        assert isinstance(decoded, NoData)
        assert wire == b""

    def test_portal_suspended(self):
        """Test PortalSuspended message."""
        msg = PortalSuspended()
        wire = msg.encode()
        decoded = PortalSuspended.decode(memoryview(wire))

        assert isinstance(decoded, PortalSuspended)
        assert wire == b""


class TestSyncAndFlush:
    """Tests for Sync and Flush messages."""

    def test_sync(self):
        """Test Sync message."""
        msg = Sync()
        wire = msg.encode()
        decoded = Sync.decode(memoryview(wire))

        assert isinstance(decoded, Sync)
        assert wire == b""

    def test_flush(self):
        """Test Flush message."""
        msg = Flush()
        wire = msg.encode()
        decoded = Flush.decode(memoryview(wire))

        assert isinstance(decoded, Flush)
        assert wire == b""


class TestParameterDescription:
    """Tests for ParameterDescription message."""

    def test_encode_no_params(self):
        """Test encoding with no parameters."""
        msg = ParameterDescription(type_oids=[])
        wire = msg.encode()

        assert wire == b"\x00\x00"

    def test_encode_with_params(self):
        """Test encoding with parameter types."""
        msg = ParameterDescription(type_oids=[23, 25, 1043])
        wire = msg.encode()

        # Should start with count=3
        assert wire[:2] == b"\x00\x03"

    def test_decode(self):
        """Test decoding ParameterDescription."""
        msg = ParameterDescription(type_oids=[23, 25])
        wire = msg.encode()
        decoded = ParameterDescription.decode(memoryview(wire))

        assert decoded.type_oids == [23, 25]

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = ParameterDescription(type_oids=[23, 25, 1043, 701])
        wire = original.encode()
        decoded = ParameterDescription.decode(memoryview(wire))

        assert decoded.type_oids == original.type_oids


class TestCopyData:
    """Tests for CopyData message (common)."""

    def test_encode(self):
        """Test encoding CopyData."""
        msg = CopyData(data=b"row1\trow2\trow3\n")
        wire = msg.encode()

        assert wire == b"row1\trow2\trow3\n"

    def test_decode(self):
        """Test decoding CopyData."""
        wire = b"some\tcopy\tdata\n"
        decoded = CopyData.decode(memoryview(wire))

        assert decoded.data == b"some\tcopy\tdata\n"

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = CopyData(data=b"binary\x00data\xff\xfe")
        wire = original.encode()
        decoded = CopyData.decode(memoryview(wire))

        assert decoded.data == original.data

    def test_empty_data(self):
        """Test CopyData with empty data."""
        msg = CopyData(data=b"")
        wire = msg.encode()
        decoded = CopyData.decode(memoryview(wire))

        assert decoded.data == b""


class TestCopyDone:
    """Tests for CopyDone message (common)."""

    def test_encode(self):
        """Test encoding CopyDone."""
        msg = CopyDone()
        wire = msg.encode()

        assert wire == b""

    def test_decode(self):
        """Test decoding CopyDone."""
        decoded = CopyDone.decode(memoryview(b""))

        assert isinstance(decoded, CopyDone)

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = CopyDone()
        wire = original.encode()
        decoded = CopyDone.decode(memoryview(wire))

        assert isinstance(decoded, CopyDone)


class TestCopyFail:
    """Tests for CopyFail message (frontend)."""

    def test_encode(self):
        """Test encoding CopyFail."""
        msg = CopyFail(error_message="user cancelled")
        wire = msg.encode()

        assert wire == b"user cancelled\x00"

    def test_decode(self):
        """Test decoding CopyFail."""
        wire = b"error occurred\x00"
        decoded = CopyFail.decode(memoryview(wire))

        assert decoded.error_message == "error occurred"

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = CopyFail(error_message="COPY aborted by user")
        wire = original.encode()
        decoded = CopyFail.decode(memoryview(wire))

        assert decoded.error_message == original.error_message

    def test_empty_message(self):
        """Test CopyFail with empty error message."""
        msg = CopyFail(error_message="")
        wire = msg.encode()
        decoded = CopyFail.decode(memoryview(wire))

        assert decoded.error_message == ""


class TestCopyInResponse:
    """Tests for CopyInResponse message (backend)."""

    def test_encode(self):
        """Test encoding CopyInResponse."""
        msg = CopyInResponse(overall_format=0, col_formats=[0, 0, 0])
        wire = msg.encode()

        # Should have format byte + Int16(3) + 3 format codes
        assert len(wire) == 1 + 2 + (2 * 3)

    def test_decode(self):
        """Test decoding CopyInResponse."""
        msg = CopyInResponse(overall_format=1, col_formats=[1, 0, 1])
        wire = msg.encode()
        decoded = CopyInResponse.decode(memoryview(wire))

        assert decoded.overall_format == 1
        assert decoded.col_formats == [1, 0, 1]

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = CopyInResponse(overall_format=0, col_formats=[0, 0, 1, 1])
        wire = original.encode()
        decoded = CopyInResponse.decode(memoryview(wire))

        assert decoded.overall_format == original.overall_format
        assert decoded.col_formats == original.col_formats


class TestCopyOutResponse:
    """Tests for CopyOutResponse message (backend)."""

    def test_encode(self):
        """Test encoding CopyOutResponse."""
        msg = CopyOutResponse(overall_format=0, col_formats=[0, 0])
        wire = msg.encode()

        assert len(wire) > 0

    def test_decode(self):
        """Test decoding CopyOutResponse."""
        msg = CopyOutResponse(overall_format=1, col_formats=[1, 1, 1])
        wire = msg.encode()
        decoded = CopyOutResponse.decode(memoryview(wire))

        assert decoded.overall_format == 1
        assert decoded.col_formats == [1, 1, 1]

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = CopyOutResponse(overall_format=0, col_formats=[0, 1, 0])
        wire = original.encode()
        decoded = CopyOutResponse.decode(memoryview(wire))

        assert decoded.overall_format == original.overall_format
        assert decoded.col_formats == original.col_formats


class TestCopyBothResponse:
    """Tests for CopyBothResponse message (backend)."""

    def test_encode(self):
        """Test encoding CopyBothResponse."""
        msg = CopyBothResponse(overall_format=0, col_formats=[0])
        wire = msg.encode()

        assert len(wire) > 0

    def test_decode(self):
        """Test decoding CopyBothResponse."""
        msg = CopyBothResponse(overall_format=1, col_formats=[1, 1])
        wire = msg.encode()
        decoded = CopyBothResponse.decode(memoryview(wire))

        assert decoded.overall_format == 1
        assert decoded.col_formats == [1, 1]

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = CopyBothResponse(overall_format=0, col_formats=[0, 0, 0, 0])
        wire = original.encode()
        decoded = CopyBothResponse.decode(memoryview(wire))

        assert decoded.overall_format == original.overall_format
        assert decoded.col_formats == original.col_formats


class TestErrorResponse:
    """Tests for ErrorResponse message."""

    def test_encode_minimal(self):
        """Test encoding ErrorResponse with minimal fields."""
        msg = ErrorResponse(fields={"S": "ERROR", "M": "test error"})
        wire = msg.encode()

        assert b"S" in wire
        assert b"ERROR\x00" in wire
        assert b"M" in wire
        assert b"test error\x00" in wire

    def test_encode_full(self):
        """Test encoding ErrorResponse with many fields."""
        msg = ErrorResponse(
            fields={
                "S": "ERROR",
                "C": "42P01",
                "M": "relation does not exist",
                "D": "The table was not found",
                "H": "Check your table name",
            }
        )
        wire = msg.encode()

        assert b"42P01\x00" in wire
        assert b"relation does not exist\x00" in wire

    def test_decode(self):
        """Test decoding ErrorResponse."""
        msg = ErrorResponse(
            fields={"S": "FATAL", "C": "28P01", "M": "password authentication failed"}
        )
        wire = msg.encode()
        decoded = ErrorResponse.decode(memoryview(wire))

        assert decoded.fields["S"] == "FATAL"
        assert decoded.fields["C"] == "28P01"
        assert decoded.fields["M"] == "password authentication failed"

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = ErrorResponse(
            fields={
                "S": "ERROR",
                "C": "22012",
                "M": "division by zero",
                "F": "numeric.c",
                "L": "1234",
            }
        )
        wire = original.encode()
        decoded = ErrorResponse.decode(memoryview(wire))

        assert decoded.fields == original.fields

    def test_properties(self):
        """Test ErrorResponse convenience properties."""
        msg = ErrorResponse(fields={"S": "ERROR", "C": "42P01", "M": "table not found"})

        assert msg.severity == "ERROR"
        assert msg.code == "42P01"
        assert msg.message == "table not found"

    def test_missing_properties(self):
        """Test properties with missing fields."""
        msg = ErrorResponse(fields={})

        assert msg.severity == ""
        assert msg.code == ""
        assert msg.message == ""


class TestNoticeResponse:
    """Tests for NoticeResponse message."""

    def test_encode(self):
        """Test encoding NoticeResponse."""
        msg = NoticeResponse(fields={"S": "NOTICE", "M": "test notice"})
        wire = msg.encode()

        assert b"NOTICE\x00" in wire
        assert b"test notice\x00" in wire

    def test_decode(self):
        """Test decoding NoticeResponse."""
        msg = NoticeResponse(fields={"S": "WARNING", "M": "deprecated feature"})
        wire = msg.encode()
        decoded = NoticeResponse.decode(memoryview(wire))

        assert decoded.fields["S"] == "WARNING"
        assert decoded.fields["M"] == "deprecated feature"

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = NoticeResponse(fields={"S": "NOTICE", "C": "00000", "M": "table was created"})
        wire = original.encode()
        decoded = NoticeResponse.decode(memoryview(wire))

        assert decoded.fields == original.fields


class TestNotificationResponse:
    """Tests for NotificationResponse message."""

    def test_encode(self):
        """Test encoding NotificationResponse."""
        msg = NotificationResponse(process_id=1234, channel="test_channel", payload="test data")
        wire = msg.encode()

        assert b"test_channel\x00" in wire
        assert b"test data\x00" in wire

    def test_decode(self):
        """Test decoding NotificationResponse."""
        msg = NotificationResponse(process_id=5678, channel="events", payload="new event")
        wire = msg.encode()
        decoded = NotificationResponse.decode(memoryview(wire))

        assert decoded.process_id == 5678
        assert decoded.channel == "events"
        assert decoded.payload == "new event"

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = NotificationResponse(process_id=9999, channel="alerts", payload="alert message")
        wire = original.encode()
        decoded = NotificationResponse.decode(memoryview(wire))

        assert decoded.process_id == original.process_id
        assert decoded.channel == original.channel
        assert decoded.payload == original.payload

    def test_empty_payload(self):
        """Test NotificationResponse with empty payload."""
        msg = NotificationResponse(process_id=1111, channel="test", payload="")
        wire = msg.encode()
        decoded = NotificationResponse.decode(memoryview(wire))

        assert decoded.payload == ""


class TestParameterStatus:
    """Tests for ParameterStatus message."""

    def test_encode(self):
        """Test encoding ParameterStatus."""
        msg = ParameterStatus(name="TimeZone", value="UTC")
        wire = msg.encode()

        assert wire == b"TimeZone\x00UTC\x00"

    def test_decode(self):
        """Test decoding ParameterStatus."""
        wire = b"client_encoding\x00UTF8\x00"
        decoded = ParameterStatus.decode(memoryview(wire))

        assert decoded.name == "client_encoding"
        assert decoded.value == "UTF8"

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = ParameterStatus(name="server_version", value="16.1")
        wire = original.encode()
        decoded = ParameterStatus.decode(memoryview(wire))

        assert decoded.name == original.name
        assert decoded.value == original.value


class TestBackendKeyData:
    """Tests for BackendKeyData message."""

    def test_encode(self):
        """Test encoding BackendKeyData."""
        msg = BackendKeyData(process_id=12345, secret_key=b"\x01\x02\x03\x04")
        wire = msg.encode()

        # Should be 4 bytes process_id + secret_key
        assert len(wire) >= 8

    def test_decode(self):
        """Test decoding BackendKeyData."""
        msg = BackendKeyData(process_id=67890, secret_key=b"test")
        wire = msg.encode()
        decoded = BackendKeyData.decode(memoryview(wire))

        assert decoded.process_id == 67890
        assert decoded.secret_key == b"test"

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = BackendKeyData(process_id=11111, secret_key=b"\xaa\xbb\xcc\xdd")
        wire = original.encode()
        decoded = BackendKeyData.decode(memoryview(wire))

        assert decoded.process_id == original.process_id
        assert decoded.secret_key == original.secret_key


class TestTerminate:
    """Tests for Terminate message (frontend)."""

    def test_encode(self):
        """Test encoding Terminate."""
        msg = Terminate()
        wire = msg.encode()

        assert wire == b""

    def test_decode(self):
        """Test decoding Terminate."""
        decoded = Terminate.decode(memoryview(b""))

        assert isinstance(decoded, Terminate)

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = Terminate()
        wire = original.encode()
        decoded = Terminate.decode(memoryview(wire))

        assert isinstance(decoded, Terminate)


class TestFunctionCall:
    """Tests for FunctionCall message (frontend)."""

    def test_encode_no_args(self):
        """Test encoding FunctionCall with no arguments."""
        msg = FunctionCall(function_oid=123, arguments=[])
        wire = msg.encode()

        # Should have OID + format codes + arg count + result format
        assert len(wire) > 0

    def test_encode_with_args(self):
        """Test encoding FunctionCall with arguments."""
        msg = FunctionCall(
            function_oid=456,
            arg_formats=[0, 0],
            arguments=[b"arg1", b"arg2"],
            result_format=0,
        )
        wire = msg.encode()

        assert b"arg1" in wire
        assert b"arg2" in wire

    def test_decode(self):
        """Test decoding FunctionCall."""
        msg = FunctionCall(function_oid=789, arguments=[b"test"])
        wire = msg.encode()
        decoded = FunctionCall.decode(memoryview(wire))

        assert decoded.function_oid == 789

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = FunctionCall(function_oid=999, arguments=[b"data1", b"data2"])
        wire = original.encode()
        decoded = FunctionCall.decode(memoryview(wire))

        assert decoded.function_oid == original.function_oid
        assert decoded.arguments == original.arguments

    def test_round_trip_with_formats(self):
        """Test encode/decode round-trip with arg_formats and result_format."""
        original = FunctionCall(
            function_oid=12345,
            arg_formats=[1, 0, 1],  # binary, text, binary
            arguments=[b"\x00\x01\x02", b"text", b"\xff\xfe"],
            result_format=1,  # binary result
        )
        wire = original.encode()
        decoded = FunctionCall.decode(memoryview(wire))

        assert decoded.function_oid == original.function_oid
        assert decoded.arg_formats == original.arg_formats
        assert decoded.arguments == original.arguments
        assert decoded.result_format == original.result_format

    def test_round_trip_with_null_argument(self):
        """Test encode/decode round-trip with NULL argument."""
        original = FunctionCall(
            function_oid=555,
            arguments=[b"first", None, b"third"],
        )
        wire = original.encode()
        decoded = FunctionCall.decode(memoryview(wire))

        assert decoded.function_oid == original.function_oid
        assert decoded.arguments == original.arguments
        assert decoded.arguments[1] is None


class TestFunctionCallResponse:
    """Tests for FunctionCallResponse message (backend)."""

    def test_encode_with_result(self):
        """Test encoding FunctionCallResponse with result."""
        msg = FunctionCallResponse(result=b"result_value")
        wire = msg.encode()

        assert b"result_value" in wire

    def test_encode_null_result(self):
        """Test encoding FunctionCallResponse with NULL result."""
        msg = FunctionCallResponse(result=None)
        wire = msg.encode()

        # Should contain -1 for NULL
        assert b"\xff\xff\xff\xff" in wire

    def test_decode(self):
        """Test decoding FunctionCallResponse."""
        msg = FunctionCallResponse(result=b"test_result")
        wire = msg.encode()
        decoded = FunctionCallResponse.decode(memoryview(wire))

        assert decoded.result == b"test_result"

    def test_decode_null(self):
        """Test decoding FunctionCallResponse with NULL."""
        msg = FunctionCallResponse(result=None)
        wire = msg.encode()
        decoded = FunctionCallResponse.decode(memoryview(wire))

        assert decoded.result is None

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = FunctionCallResponse(result=b"function_output")
        wire = original.encode()
        decoded = FunctionCallResponse.decode(memoryview(wire))

        assert decoded.result == original.result


class TestNegotiateProtocolVersion:
    """Tests for NegotiateProtocolVersion message (backend)."""

    def test_encode(self):
        """Test encoding NegotiateProtocolVersion."""
        msg = NegotiateProtocolVersion(
            newest_minor=0,  # 3.0
            unrecognized=["option1", "option2"],
        )
        wire = msg.encode()

        assert b"option1\x00" in wire
        assert b"option2\x00" in wire

    def test_decode(self):
        """Test decoding NegotiateProtocolVersion."""
        msg = NegotiateProtocolVersion(newest_minor=0, unrecognized=["test_option"])
        wire = msg.encode()
        decoded = NegotiateProtocolVersion.decode(memoryview(wire))

        assert decoded.newest_minor == 0
        assert decoded.unrecognized == ["test_option"]

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = NegotiateProtocolVersion(
            newest_minor=2,  # 3.2
            unrecognized=["opt1", "opt2", "opt3"],
        )
        wire = original.encode()
        decoded = NegotiateProtocolVersion.decode(memoryview(wire))

        assert decoded.newest_minor == original.newest_minor
        assert decoded.unrecognized == original.unrecognized

    def test_no_unrecognized_options(self):
        """Test NegotiateProtocolVersion with no unrecognized options."""
        msg = NegotiateProtocolVersion(newest_minor=0, unrecognized=[])
        wire = msg.encode()
        decoded = NegotiateProtocolVersion.decode(memoryview(wire))

        assert decoded.unrecognized == []
