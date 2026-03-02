"""Unit tests for simple query protocol messages."""

from pygwire.constants import BackendMessageType, FrontendMessageType, TransactionStatus
from pygwire.messages import (
    CommandComplete,
    DataRow,
    EmptyQueryResponse,
    FieldDescription,
    Query,
    ReadyForQuery,
    RowDescription,
)


class TestQuery:
    """Tests for Query message encoding/decoding."""

    def test_encode_simple_query(self):
        """Test encoding a simple query."""
        msg = Query(query_string="SELECT 1")
        wire = msg.encode()

        assert wire == b"SELECT 1\x00"

    def test_encode_empty_query(self):
        """Test encoding an empty query."""
        msg = Query(query_string="")
        wire = msg.encode()

        assert wire == b"\x00"

    def test_encode_complex_query(self):
        """Test encoding a complex query."""
        sql = "SELECT * FROM users WHERE id = 42 AND name = 'test'"
        msg = Query(query_string=sql)
        wire = msg.encode()

        assert wire == sql.encode("utf-8") + b"\x00"

    def test_decode_simple_query(self):
        """Test decoding a simple query."""
        wire = b"SELECT 1\x00"
        decoded = Query.decode(memoryview(wire))

        assert decoded.query_string == "SELECT 1"

    def test_decode_empty_query(self):
        """Test decoding an empty query."""
        wire = b"\x00"
        decoded = Query.decode(memoryview(wire))

        assert decoded.query_string == ""

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = Query(query_string="SELECT * FROM products WHERE price > 100")
        wire = original.encode()
        decoded = Query.decode(memoryview(wire))

        assert decoded.query_string == original.query_string

    def test_unicode_query(self):
        """Test encoding/decoding query with Unicode."""
        msg = Query(query_string="SELECT '你好' AS greeting")
        wire = msg.encode()
        decoded = Query.decode(memoryview(wire))

        assert decoded.query_string == msg.query_string

    def test_multiline_query(self):
        """Test encoding/decoding multiline query."""
        sql = """SELECT *
FROM users
WHERE age > 18
ORDER BY name"""
        msg = Query(query_string=sql)
        wire = msg.encode()
        decoded = Query.decode(memoryview(wire))

        assert decoded.query_string == sql

    def test_identifier(self):
        """Test Query has correct identifier."""
        msg = Query(query_string="SELECT 1")
        assert msg.identifier == FrontendMessageType.QUERY.encode("ascii")

    def test_to_wire(self):
        """Test Query.to_wire() includes proper framing."""
        msg = Query(query_string="SELECT 1")
        wire = msg.to_wire()

        # Should be: 'Q' + Int32(length) + payload
        assert wire[0:1] == b"Q"
        length = int.from_bytes(wire[1:5], "big")
        assert length == len(wire) - 1  # Length excludes identifier byte

    def test_default_query_string(self):
        """Test Query default initialization."""
        msg = Query()
        assert msg.query_string == ""


class TestRowDescription:
    """Tests for RowDescription message encoding/decoding."""

    def test_encode_empty_fields(self):
        """Test encoding RowDescription with no fields."""
        msg = RowDescription(fields=[])
        wire = msg.encode()

        # Should be just Int16(0) for field count
        assert wire == b"\x00\x00"

    def test_encode_single_field(self):
        """Test encoding RowDescription with one field."""
        field = FieldDescription(
            name="id",
            table_oid=12345,
            column_attr=1,
            type_oid=23,  # INT4
            type_size=4,
            type_modifier=-1,
            format_code=0,
        )
        msg = RowDescription(fields=[field])
        wire = msg.encode()

        # Should start with field count
        assert wire[:2] == b"\x00\x01"
        # Should contain field name
        assert b"id\x00" in wire

    def test_encode_multiple_fields(self):
        """Test encoding RowDescription with multiple fields."""
        fields = [
            FieldDescription(name="id", type_oid=23, type_size=4),
            FieldDescription(name="name", type_oid=25, type_size=-1),
            FieldDescription(name="age", type_oid=23, type_size=4),
        ]
        msg = RowDescription(fields=fields)
        wire = msg.encode()

        # Should start with field count = 3
        assert wire[:2] == b"\x00\x03"
        # Should contain all field names
        assert b"id\x00" in wire
        assert b"name\x00" in wire
        assert b"age\x00" in wire

    def test_decode_empty_fields(self):
        """Test decoding RowDescription with no fields."""
        wire = b"\x00\x00"
        decoded = RowDescription.decode(memoryview(wire))

        assert decoded.fields == []

    def test_decode_single_field(self):
        """Test decoding RowDescription with one field."""
        field = FieldDescription(
            name="column1",
            table_oid=100,
            column_attr=1,
            type_oid=23,
            type_size=4,
            type_modifier=-1,
            format_code=0,
        )
        msg = RowDescription(fields=[field])
        wire = msg.encode()

        decoded = RowDescription.decode(memoryview(wire))
        assert len(decoded.fields) == 1
        assert decoded.fields[0].name == "column1"
        assert decoded.fields[0].table_oid == 100
        assert decoded.fields[0].type_oid == 23

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        fields = [
            FieldDescription(
                name="id",
                table_oid=16384,
                column_attr=1,
                type_oid=23,
                type_size=4,
                type_modifier=-1,
                format_code=0,
            ),
            FieldDescription(
                name="username",
                table_oid=16384,
                column_attr=2,
                type_oid=25,
                type_size=-1,
                type_modifier=-1,
                format_code=0,
            ),
        ]
        original = RowDescription(fields=fields)
        wire = original.encode()
        decoded = RowDescription.decode(memoryview(wire))

        assert len(decoded.fields) == len(original.fields)
        for i, field in enumerate(decoded.fields):
            orig = original.fields[i]
            assert field.name == orig.name
            assert field.table_oid == orig.table_oid
            assert field.column_attr == orig.column_attr
            assert field.type_oid == orig.type_oid
            assert field.type_size == orig.type_size
            assert field.type_modifier == orig.type_modifier
            assert field.format_code == orig.format_code

    def test_identifier(self):
        """Test RowDescription has correct identifier."""
        msg = RowDescription(fields=[])
        assert msg.identifier == BackendMessageType.ROW_DESCRIPTION.encode("ascii")

    def test_binary_format_code(self):
        """Test RowDescription with binary format."""
        field = FieldDescription(name="data", format_code=1)
        msg = RowDescription(fields=[field])
        wire = msg.encode()
        decoded = RowDescription.decode(memoryview(wire))

        assert decoded.fields[0].format_code == 1


class TestDataRow:
    """Tests for DataRow message encoding/decoding."""

    def test_encode_empty_row(self):
        """Test encoding DataRow with no columns."""
        msg = DataRow(columns=[])
        wire = msg.encode()

        # Should be just Int16(0) for column count
        assert wire == b"\x00\x00"

    def test_encode_single_column(self):
        """Test encoding DataRow with one column."""
        msg = DataRow(columns=[b"value1"])
        wire = msg.encode()

        # Int16(1) + Int32(6) + b"value1"
        assert wire[:2] == b"\x00\x01"  # Column count
        assert wire[2:6] == b"\x00\x00\x00\x06"  # Value length
        assert wire[6:] == b"value1"

    def test_encode_multiple_columns(self):
        """Test encoding DataRow with multiple columns."""
        msg = DataRow(columns=[b"col1", b"col2", b"col3"])
        wire = msg.encode()

        # Should start with column count = 3
        assert wire[:2] == b"\x00\x03"

    def test_encode_null_column(self):
        """Test encoding DataRow with NULL value."""
        msg = DataRow(columns=[None])
        wire = msg.encode()

        # Int16(1) + Int32(-1) for NULL
        assert wire == b"\x00\x01\xff\xff\xff\xff"

    def test_encode_mixed_columns(self):
        """Test encoding DataRow with mix of values and NULLs."""
        msg = DataRow(columns=[b"value1", None, b"value3"])
        wire = msg.encode()

        # Should start with column count = 3
        assert wire[:2] == b"\x00\x03"

    def test_decode_empty_row(self):
        """Test decoding DataRow with no columns."""
        wire = b"\x00\x00"
        decoded = DataRow.decode(memoryview(wire))

        assert decoded.columns == []

    def test_decode_single_column(self):
        """Test decoding DataRow with one column."""
        msg = DataRow(columns=[b"test"])
        wire = msg.encode()

        decoded = DataRow.decode(memoryview(wire))
        assert decoded.columns == [b"test"]

    def test_decode_multiple_columns(self):
        """Test decoding DataRow with multiple columns."""
        msg = DataRow(columns=[b"a", b"b", b"c"])
        wire = msg.encode()

        decoded = DataRow.decode(memoryview(wire))
        assert decoded.columns == [b"a", b"b", b"c"]

    def test_decode_null_column(self):
        """Test decoding DataRow with NULL value."""
        msg = DataRow(columns=[None])
        wire = msg.encode()

        decoded = DataRow.decode(memoryview(wire))
        assert decoded.columns == [None]

    def test_decode_mixed_columns(self):
        """Test decoding DataRow with mix of values and NULLs."""
        msg = DataRow(columns=[b"first", None, b"third", None, b"fifth"])
        wire = msg.encode()

        decoded = DataRow.decode(memoryview(wire))
        assert decoded.columns == [b"first", None, b"third", None, b"fifth"]

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = DataRow(columns=[b"value1", b"longer_value_here", None, b"", b"final"])
        wire = original.encode()
        decoded = DataRow.decode(memoryview(wire))

        assert decoded.columns == original.columns

    def test_identifier(self):
        """Test DataRow has correct identifier."""
        msg = DataRow(columns=[])
        assert msg.identifier == BackendMessageType.DATA_ROW.encode("ascii")

    def test_empty_string_column(self):
        """Test DataRow with empty string (not NULL)."""
        msg = DataRow(columns=[b""])
        wire = msg.encode()

        # Should encode length=0, not -1 (which is NULL)
        decoded = DataRow.decode(memoryview(wire))
        assert decoded.columns == [b""]
        assert decoded.columns[0] is not None

    def test_binary_data(self):
        """Test DataRow with binary data."""
        binary_data = bytes(range(256))
        msg = DataRow(columns=[binary_data])
        wire = msg.encode()
        decoded = DataRow.decode(memoryview(wire))

        assert decoded.columns[0] == binary_data


class TestCommandComplete:
    """Tests for CommandComplete message encoding/decoding."""

    def test_encode_select_tag(self):
        """Test encoding CommandComplete with SELECT tag."""
        msg = CommandComplete(tag="SELECT 42")
        wire = msg.encode()

        assert wire == b"SELECT 42\x00"

    def test_encode_insert_tag(self):
        """Test encoding CommandComplete with INSERT tag."""
        msg = CommandComplete(tag="INSERT 0 1")
        wire = msg.encode()

        assert wire == b"INSERT 0 1\x00"

    def test_encode_update_tag(self):
        """Test encoding CommandComplete with UPDATE tag."""
        msg = CommandComplete(tag="UPDATE 5")
        wire = msg.encode()

        assert wire == b"UPDATE 5\x00"

    def test_encode_delete_tag(self):
        """Test encoding CommandComplete with DELETE tag."""
        msg = CommandComplete(tag="DELETE 10")
        wire = msg.encode()

        assert wire == b"DELETE 10\x00"

    def test_decode(self):
        """Test decoding CommandComplete."""
        wire = b"SELECT 100\x00"
        decoded = CommandComplete.decode(memoryview(wire))

        assert decoded.tag == "SELECT 100"

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = CommandComplete(tag="CREATE TABLE")
        wire = original.encode()
        decoded = CommandComplete.decode(memoryview(wire))

        assert decoded.tag == original.tag

    def test_identifier(self):
        """Test CommandComplete has correct identifier."""
        msg = CommandComplete(tag="SELECT 1")
        assert msg.identifier == BackendMessageType.COMMAND_COMPLETE.encode("ascii")

    def test_empty_tag(self):
        """Test CommandComplete with empty tag."""
        msg = CommandComplete(tag="")
        wire = msg.encode()
        decoded = CommandComplete.decode(memoryview(wire))

        assert decoded.tag == ""

    def test_default_tag(self):
        """Test CommandComplete default initialization."""
        msg = CommandComplete()
        assert msg.tag == ""


class TestReadyForQuery:
    """Tests for ReadyForQuery message encoding/decoding."""

    def test_encode_idle_status(self):
        """Test encoding ReadyForQuery with IDLE status."""
        msg = ReadyForQuery(status=TransactionStatus.IDLE)
        wire = msg.encode()

        assert wire == b"I"

    def test_encode_in_transaction_status(self):
        """Test encoding ReadyForQuery with IN_TRANSACTION status."""
        msg = ReadyForQuery(status=TransactionStatus.IN_TRANSACTION)
        wire = msg.encode()

        assert wire == b"T"

    def test_encode_error_transaction_status(self):
        """Test encoding ReadyForQuery with ERROR_TRANSACTION status."""
        msg = ReadyForQuery(status=TransactionStatus.ERROR_TRANSACTION)
        wire = msg.encode()

        assert wire == b"E"

    def test_decode_idle_status(self):
        """Test decoding ReadyForQuery with IDLE status."""
        wire = b"I"
        decoded = ReadyForQuery.decode(memoryview(wire))

        assert decoded.status == TransactionStatus.IDLE

    def test_decode_in_transaction_status(self):
        """Test decoding ReadyForQuery with IN_TRANSACTION status."""
        wire = b"T"
        decoded = ReadyForQuery.decode(memoryview(wire))

        assert decoded.status == TransactionStatus.IN_TRANSACTION

    def test_decode_error_transaction_status(self):
        """Test decoding ReadyForQuery with ERROR_TRANSACTION status."""
        wire = b"E"
        decoded = ReadyForQuery.decode(memoryview(wire))

        assert decoded.status == TransactionStatus.ERROR_TRANSACTION

    def test_round_trip(self):
        """Test encode/decode round-trip for all statuses."""
        for status in TransactionStatus:
            original = ReadyForQuery(status=status)
            wire = original.encode()
            decoded = ReadyForQuery.decode(memoryview(wire))

            assert decoded.status == original.status

    def test_identifier(self):
        """Test ReadyForQuery has correct identifier."""
        msg = ReadyForQuery(status=TransactionStatus.IDLE)
        assert msg.identifier == BackendMessageType.READY_FOR_QUERY.encode("ascii")

    def test_default_status(self):
        """Test ReadyForQuery default initialization."""
        msg = ReadyForQuery()
        assert msg.status == TransactionStatus.IDLE


class TestEmptyQueryResponse:
    """Tests for EmptyQueryResponse message encoding/decoding."""

    def test_encode(self):
        """Test encoding EmptyQueryResponse."""
        msg = EmptyQueryResponse()
        wire = msg.encode()

        # Should be empty payload
        assert wire == b""

    def test_decode(self):
        """Test decoding EmptyQueryResponse."""
        wire = b""
        decoded = EmptyQueryResponse.decode(memoryview(wire))

        assert isinstance(decoded, EmptyQueryResponse)

    def test_round_trip(self):
        """Test encode/decode round-trip."""
        original = EmptyQueryResponse()
        wire = original.encode()
        decoded = EmptyQueryResponse.decode(memoryview(wire))

        assert isinstance(decoded, EmptyQueryResponse)

    def test_identifier(self):
        """Test EmptyQueryResponse has correct identifier."""
        msg = EmptyQueryResponse()
        assert msg.identifier == BackendMessageType.EMPTY_QUERY_RESPONSE.encode("ascii")

    def test_to_wire(self):
        """Test EmptyQueryResponse.to_wire() includes proper framing."""
        msg = EmptyQueryResponse()
        wire = msg.to_wire()

        # Should be: 'I' + Int32(4) (only the length, no payload)
        assert wire == b"I\x00\x00\x00\x04"


class TestFieldDescription:
    """Tests for FieldDescription dataclass."""

    def test_default_initialization(self):
        """Test FieldDescription with defaults."""
        field = FieldDescription()

        assert field.name == ""
        assert field.table_oid == 0
        assert field.column_attr == 0
        assert field.type_oid == 0
        assert field.type_size == 0
        assert field.type_modifier == 0
        assert field.format_code == 0

    def test_full_initialization(self):
        """Test FieldDescription with all parameters."""
        field = FieldDescription(
            name="test_col",
            table_oid=12345,
            column_attr=1,
            type_oid=23,
            type_size=4,
            type_modifier=-1,
            format_code=1,
        )

        assert field.name == "test_col"
        assert field.table_oid == 12345
        assert field.column_attr == 1
        assert field.type_oid == 23
        assert field.type_size == 4
        assert field.type_modifier == -1
        assert field.format_code == 1

    def test_text_format(self):
        """Test FieldDescription with text format (format_code=0)."""
        field = FieldDescription(name="col", format_code=0)
        assert field.format_code == 0

    def test_binary_format(self):
        """Test FieldDescription with binary format (format_code=1)."""
        field = FieldDescription(name="col", format_code=1)
        assert field.format_code == 1
