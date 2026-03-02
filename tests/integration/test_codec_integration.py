"""Integration tests for codec and message parsing."""

from pygwire.codec import BackendMessageDecoder, FrontendMessageDecoder
from pygwire.constants import TransactionStatus
from pygwire.messages import (
    AuthenticationMD5Password,
    AuthenticationOk,
    AuthenticationSASL,
    BackendKeyData,
    Bind,
    BindComplete,
    CommandComplete,
    CopyData,
    CopyDone,
    CopyInResponse,
    DataRow,
    Execute,
    FieldDescription,
    NotificationResponse,
    ParameterStatus,
    Parse,
    ParseComplete,
    PasswordMessage,
    Query,
    ReadyForQuery,
    RowDescription,
    SSLRequest,
    StartupMessage,
    Sync,
)


class TestStartupSequence:
    """Integration tests for startup message sequences."""

    def test_ssl_then_startup(self):
        """Test SSL request followed by startup message."""
        decoder = FrontendMessageDecoder(startup=True)

        # SSL Request
        ssl_req = SSLRequest()
        decoder.feed(ssl_req.to_wire())
        decoded = decoder.read()
        assert isinstance(decoded, SSLRequest)

        # After SSL (hypothetically accepted), send startup
        startup = StartupMessage(params={"user": "testuser", "database": "testdb"})
        decoder.feed(startup.to_wire())
        decoded = decoder.read()
        assert isinstance(decoded, StartupMessage)
        assert decoded.params["user"] == "testuser"

        # Decoder should have exited startup mode
        assert not decoder.in_startup

    def test_startup_auth_ready_sequence(self):
        """Test full startup sequence: startup -> auth -> ready."""
        # Frontend decoder (receiving backend messages)
        frontend_decoder = BackendMessageDecoder()

        # Receive AuthenticationOk
        auth_ok = AuthenticationOk()
        frontend_decoder.feed(auth_ok.to_wire())
        decoded = frontend_decoder.read()
        assert isinstance(decoded, AuthenticationOk)

        # Receive BackendKeyData
        key_data = BackendKeyData(process_id=12345, secret_key=b"test")
        frontend_decoder.feed(key_data.to_wire())
        decoded = frontend_decoder.read()
        assert isinstance(decoded, BackendKeyData)
        assert decoded.process_id == 12345

        # Receive ReadyForQuery
        ready = ReadyForQuery(status=TransactionStatus.IDLE)
        frontend_decoder.feed(ready.to_wire())
        decoded = frontend_decoder.read()
        assert isinstance(decoded, ReadyForQuery)
        assert decoded.status == TransactionStatus.IDLE


class TestSimpleQuerySequence:
    """Integration tests for simple query protocol sequences."""

    def test_simple_query_flow(self):
        """Test complete simple query request and response."""
        # Frontend sends query
        frontend_decoder = FrontendMessageDecoder()
        query = Query(query_string="SELECT id, name FROM users")
        frontend_decoder.feed(query.to_wire())
        decoded_query = frontend_decoder.read()
        assert isinstance(decoded_query, Query)
        assert "users" in decoded_query.query_string

        # Backend responds with results
        backend_decoder = BackendMessageDecoder()

        # RowDescription
        row_desc = RowDescription(
            fields=[
                FieldDescription(name="id", type_oid=23, type_size=4),
                FieldDescription(name="name", type_oid=25, type_size=-1),
            ]
        )
        backend_decoder.feed(row_desc.to_wire())
        decoded = backend_decoder.read()
        assert isinstance(decoded, RowDescription)
        assert len(decoded.fields) == 2
        assert decoded.fields[0].name == "id"

        # DataRow
        data_row = DataRow(columns=[b"1", b"Alice"])
        backend_decoder.feed(data_row.to_wire())
        decoded = backend_decoder.read()
        assert isinstance(decoded, DataRow)
        assert decoded.columns == [b"1", b"Alice"]

        # CommandComplete
        cmd_complete = CommandComplete(tag="SELECT 1")
        backend_decoder.feed(cmd_complete.to_wire())
        decoded = backend_decoder.read()
        assert isinstance(decoded, CommandComplete)

        # ReadyForQuery
        ready = ReadyForQuery(status=TransactionStatus.IDLE)
        backend_decoder.feed(ready.to_wire())
        decoded = backend_decoder.read()
        assert isinstance(decoded, ReadyForQuery)

    def test_multiple_rows(self):
        """Test simple query with multiple result rows."""
        decoder = BackendMessageDecoder()

        rows = [
            DataRow(columns=[b"1", b"Alice"]),
            DataRow(columns=[b"2", b"Bob"]),
            DataRow(columns=[b"3", b"Charlie"]),
        ]

        # Feed all rows at once
        wire_data = b""
        for row in rows:
            wire_data += row.to_wire()

        decoder.feed(wire_data)

        # Read all rows
        decoded_rows = decoder.read_all()
        assert len(decoded_rows) == 3
        assert all(isinstance(r, DataRow) for r in decoded_rows)
        assert decoded_rows[1].columns == [b"2", b"Bob"]


class TestExtendedQuerySequence:
    """Integration tests for extended query protocol sequences."""

    def test_parse_bind_execute_flow(self):
        """Test complete Parse/Bind/Execute/Sync flow."""
        # Frontend sends Parse
        frontend_decoder = FrontendMessageDecoder()
        parse = Parse(statement="stmt1", query="SELECT $1", param_types=[23])
        frontend_decoder.feed(parse.to_wire())
        decoded = frontend_decoder.read()
        assert isinstance(decoded, Parse)
        assert decoded.statement == "stmt1"

        # Backend responds with ParseComplete
        backend_decoder = BackendMessageDecoder()
        parse_complete = ParseComplete()
        backend_decoder.feed(parse_complete.to_wire())
        decoded = backend_decoder.read()
        assert isinstance(decoded, ParseComplete)

        # Frontend sends Bind
        bind = Bind(portal="", statement="stmt1", param_values=[b"42"])
        frontend_decoder.feed(bind.to_wire())
        decoded = frontend_decoder.read()
        assert isinstance(decoded, Bind)

        # Backend responds with BindComplete
        bind_complete = BindComplete()
        backend_decoder.feed(bind_complete.to_wire())
        decoded = backend_decoder.read()
        assert isinstance(decoded, BindComplete)

        # Frontend sends Execute
        execute = Execute(portal="", max_rows=0)
        frontend_decoder.feed(execute.to_wire())
        decoded = frontend_decoder.read()
        assert isinstance(decoded, Execute)

        # Backend sends results and CommandComplete
        data_row = DataRow(columns=[b"42"])
        cmd_complete = CommandComplete(tag="SELECT 1")
        backend_decoder.feed(data_row.to_wire() + cmd_complete.to_wire())
        decoded1 = backend_decoder.read()
        decoded2 = backend_decoder.read()
        assert isinstance(decoded1, DataRow)
        assert isinstance(decoded2, CommandComplete)

        # Frontend sends Sync
        sync = Sync()
        frontend_decoder.feed(sync.to_wire())
        decoded = frontend_decoder.read()
        assert isinstance(decoded, Sync)

        # Backend sends ReadyForQuery
        ready = ReadyForQuery(status=TransactionStatus.IDLE)
        backend_decoder.feed(ready.to_wire())
        decoded = backend_decoder.read()
        assert isinstance(decoded, ReadyForQuery)

    def test_pipelined_extended_query(self):
        """Test pipelining Parse, Bind, Execute, Sync."""
        decoder = FrontendMessageDecoder()

        # Create pipelined messages
        parse = Parse(statement="s1", query="SELECT $1", param_types=[23])
        bind = Bind(portal="", statement="s1", param_values=[b"100"])
        execute = Execute(portal="", max_rows=0)
        sync = Sync()

        # Send all at once
        wire = parse.to_wire() + bind.to_wire() + execute.to_wire() + sync.to_wire()
        decoder.feed(wire)

        # Read all messages
        messages = decoder.read_all()
        assert len(messages) == 4
        assert isinstance(messages[0], Parse)
        assert isinstance(messages[1], Bind)
        assert isinstance(messages[2], Execute)
        assert isinstance(messages[3], Sync)


class TestCopyProtocol:
    """Integration tests for COPY protocol."""

    def test_copy_in_sequence(self):
        """Test COPY IN protocol flow."""
        # Backend sends CopyInResponse
        backend_decoder = BackendMessageDecoder()
        copy_in = CopyInResponse(overall_format=0, col_formats=[0, 0])
        backend_decoder.feed(copy_in.to_wire())
        decoded = backend_decoder.read()
        assert isinstance(decoded, CopyInResponse)

        # Frontend sends CopyData messages
        frontend_decoder = FrontendMessageDecoder()
        copy_data1 = CopyData(data=b"row1\tdata1\n")
        copy_data2 = CopyData(data=b"row2\tdata2\n")
        copy_done = CopyDone()

        wire = copy_data1.to_wire() + copy_data2.to_wire() + copy_done.to_wire()
        frontend_decoder.feed(wire)

        messages = frontend_decoder.read_all()
        assert len(messages) == 3
        assert isinstance(messages[0], CopyData)
        assert isinstance(messages[1], CopyData)
        assert isinstance(messages[2], CopyDone)

        # Backend sends CommandComplete and ReadyForQuery
        cmd_complete = CommandComplete(tag="COPY 2")
        ready = ReadyForQuery(status=TransactionStatus.IDLE)
        backend_decoder.feed(cmd_complete.to_wire() + ready.to_wire())

        decoded1 = backend_decoder.read()
        decoded2 = backend_decoder.read()
        assert isinstance(decoded1, CommandComplete)
        assert decoded2.status == TransactionStatus.IDLE


class TestAuthenticationSequences:
    """Integration tests for various authentication flows."""

    def test_md5_auth_flow(self):
        """Test MD5 authentication flow."""
        # Backend sends AuthenticationMD5Password
        backend_decoder = BackendMessageDecoder()
        auth_md5 = AuthenticationMD5Password(salt=b"\x01\x02\x03\x04")
        backend_decoder.feed(auth_md5.to_wire())
        decoded = backend_decoder.read()
        assert isinstance(decoded, AuthenticationMD5Password)
        assert decoded.salt == b"\x01\x02\x03\x04"

        # Frontend sends PasswordMessage with hashed password
        frontend_decoder = FrontendMessageDecoder()
        password = PasswordMessage(password="md5" + "0" * 32)  # Simulated MD5 hash
        frontend_decoder.feed(password.to_wire())
        decoded = frontend_decoder.read()
        assert isinstance(decoded, PasswordMessage)

        # Backend sends AuthenticationOk
        auth_ok = AuthenticationOk()
        backend_decoder.feed(auth_ok.to_wire())
        decoded = backend_decoder.read()
        assert isinstance(decoded, AuthenticationOk)

    def test_sasl_auth_flow(self):
        """Test SASL authentication flow."""
        backend_decoder = BackendMessageDecoder()

        # Backend offers SASL mechanisms
        auth_sasl = AuthenticationSASL(mechanisms=["SCRAM-SHA-256"])
        backend_decoder.feed(auth_sasl.to_wire())
        decoded = backend_decoder.read()
        assert isinstance(decoded, AuthenticationSASL)
        assert "SCRAM-SHA-256" in decoded.mechanisms


class TestAsyncNotifications:
    """Integration tests for asynchronous notifications."""

    def test_notification_during_idle(self):
        """Test receiving notification while idle."""
        decoder = BackendMessageDecoder()

        # Interleave notifications with ParameterStatus
        notification = NotificationResponse(process_id=1234, channel="events", payload="new_event")
        param_status = ParameterStatus(name="TimeZone", value="UTC")

        wire = notification.to_wire() + param_status.to_wire()
        decoder.feed(wire)

        messages = decoder.read_all()
        assert len(messages) == 2
        assert isinstance(messages[0], NotificationResponse)
        assert messages[0].channel == "events"
        assert isinstance(messages[1], ParameterStatus)

    def test_notification_during_query(self):
        """Test receiving notification during query execution."""
        decoder = BackendMessageDecoder()

        # Notification arrives during result streaming
        row1 = DataRow(columns=[b"value1"])
        notification = NotificationResponse(process_id=5678, channel="alerts", payload="alert_data")
        row2 = DataRow(columns=[b"value2"])

        wire = row1.to_wire() + notification.to_wire() + row2.to_wire()
        decoder.feed(wire)

        messages = decoder.read_all()
        assert len(messages) == 3
        assert isinstance(messages[0], DataRow)
        assert isinstance(messages[1], NotificationResponse)
        assert isinstance(messages[2], DataRow)


class TestStreamingAndBuffering:
    """Integration tests for streaming and buffer management."""

    def test_incremental_feed(self):
        """Test feeding message byte by byte."""
        decoder = FrontendMessageDecoder()
        msg = Query(query_string="SELECT 1")
        wire = msg.to_wire()

        # Feed one byte at a time
        for i, byte in enumerate(wire):
            decoder.feed(bytes([byte]))
            if i < len(wire) - 1:
                # Should not be complete yet
                assert decoder.read() is None

        # Last byte should complete the message
        decoded = decoder.read()
        assert isinstance(decoded, Query)
        assert decoded.query_string == "SELECT 1"

    def test_large_batch_of_messages(self):
        """Test decoding large batch of messages."""
        decoder = FrontendMessageDecoder()

        # Create 1000 query messages
        messages = []
        wire_data = b""
        for i in range(1000):
            msg = Query(query_string=f"SELECT {i}")
            messages.append(msg)
            wire_data += msg.to_wire()

        # Feed all at once
        decoder.feed(wire_data)

        # Decode all
        decoded = decoder.read_all()
        assert len(decoded) == 1000
        assert all(isinstance(m, Query) for m in decoded)
        assert decoded[500].query_string == "SELECT 500"

    def test_partial_message_across_feeds(self):
        """Test message split across multiple feeds."""
        decoder = FrontendMessageDecoder()
        msg = Query(query_string="SELECT * FROM large_table WHERE condition = true")
        wire = msg.to_wire()

        # Split at various points
        split_point = len(wire) // 3
        decoder.feed(wire[:split_point])
        assert decoder.read() is None

        decoder.feed(wire[split_point : split_point * 2])
        assert decoder.read() is None

        decoder.feed(wire[split_point * 2 :])
        decoded = decoder.read()
        assert isinstance(decoded, Query)
        assert decoded.query_string == msg.query_string

    def test_buffer_compaction(self):
        """Test that buffer is compacted efficiently."""
        decoder = FrontendMessageDecoder()

        # Feed and consume many small messages
        for i in range(200):
            msg = Query(query_string=f"Q{i}")
            decoder.feed(msg.to_wire())
            decoded = decoder.read()
            assert isinstance(decoded, Query)

        # Buffer should be empty or minimal
        assert decoder.buffered == 0

    def test_mixed_message_sizes(self):
        """Test handling messages of varying sizes."""
        decoder = FrontendMessageDecoder()

        messages = [
            Query(query_string="SELECT 1"),
            Query(query_string="SELECT * FROM " + "x" * 1000),  # Large
            Query(query_string=""),  # Empty
            Query(
                query_string="SELECT * FROM users WHERE id IN ("
                + ",".join([str(i) for i in range(100)])
                + ")"
            ),
        ]

        wire_data = b"".join(msg.to_wire() for msg in messages)
        decoder.feed(wire_data)

        decoded = decoder.read_all()
        assert len(decoded) == len(messages)
        for i, msg in enumerate(decoded):
            assert msg.query_string == messages[i].query_string


class TestErrorScenarios:
    """Integration tests for error scenarios."""

    def test_clear_removes_partial_message(self):
        """Test that clear() removes partial buffered message."""
        decoder = FrontendMessageDecoder()
        msg = Query(query_string="SELECT 1")
        wire = msg.to_wire()

        # Feed partial message
        decoder.feed(wire[:10])
        assert decoder.buffered > 0

        # Clear should remove everything
        decoder.clear()
        assert decoder.buffered == 0
        assert decoder.read() is None

        # Can continue using decoder
        decoder.feed(msg.to_wire())
        decoded = decoder.read()
        assert isinstance(decoded, Query)

    def test_interleaved_modes(self):
        """Test frontend and backend decoders work independently."""
        frontend_decoder = FrontendMessageDecoder()
        backend_decoder = BackendMessageDecoder()

        # Frontend message
        query = Query(query_string="SELECT 1")
        frontend_decoder.feed(query.to_wire())
        decoded = frontend_decoder.read()
        assert isinstance(decoded, Query)

        # Backend message
        ready = ReadyForQuery(status=TransactionStatus.IDLE)
        backend_decoder.feed(ready.to_wire())
        decoded = backend_decoder.read()
        assert isinstance(decoded, ReadyForQuery)

        # Both decoders work correctly
        assert True  # BackendMessageDecoder used for frontend
        assert True  # FrontendMessageDecoder used for backend


class TestRealWorldScenarios:
    """Integration tests simulating real-world usage patterns."""

    def test_connection_lifecycle(self):
        """Test complete connection lifecycle."""
        # Startup phase
        startup_decoder = FrontendMessageDecoder(startup=True)
        startup = StartupMessage(params={"user": "app", "database": "prod"})
        startup_decoder.feed(startup.to_wire())
        decoded = startup_decoder.read()
        assert isinstance(decoded, StartupMessage)

        # Authentication phase (backend)
        backend_decoder = BackendMessageDecoder()
        auth_ok = AuthenticationOk()
        backend_decoder.feed(auth_ok.to_wire())
        decoded = backend_decoder.read()
        assert isinstance(decoded, AuthenticationOk)

        # Ready for queries
        ready = ReadyForQuery(status=TransactionStatus.IDLE)
        backend_decoder.feed(ready.to_wire())
        decoded = backend_decoder.read()
        assert decoded.status == TransactionStatus.IDLE

        # Execute queries (frontend)
        frontend_decoder = FrontendMessageDecoder()
        query = Query(query_string="SELECT version()")
        frontend_decoder.feed(query.to_wire())
        decoded = frontend_decoder.read()
        assert isinstance(decoded, Query)

        # Results (backend)
        row_desc = RowDescription(fields=[FieldDescription(name="version")])
        data_row = DataRow(columns=[b"PostgreSQL 16.1"])
        cmd_complete = CommandComplete(tag="SELECT 1")
        ready = ReadyForQuery(status=TransactionStatus.IDLE)

        wire = row_desc.to_wire() + data_row.to_wire() + cmd_complete.to_wire() + ready.to_wire()
        backend_decoder.feed(wire)

        messages = backend_decoder.read_all()
        assert len(messages) == 4
        assert isinstance(messages[0], RowDescription)
        assert isinstance(messages[1], DataRow)
        assert isinstance(messages[2], CommandComplete)
        assert isinstance(messages[3], ReadyForQuery)

    def test_transaction_workflow(self):
        """Test transaction BEGIN/COMMIT workflow."""
        backend_decoder = BackendMessageDecoder()

        # BEGIN
        cmd1 = CommandComplete(tag="BEGIN")
        ready1 = ReadyForQuery(status=TransactionStatus.IN_TRANSACTION)
        backend_decoder.feed(cmd1.to_wire() + ready1.to_wire())

        decoded = backend_decoder.read_all()
        assert decoded[1].status == TransactionStatus.IN_TRANSACTION

        # COMMIT
        cmd2 = CommandComplete(tag="COMMIT")
        ready2 = ReadyForQuery(status=TransactionStatus.IDLE)
        backend_decoder.feed(cmd2.to_wire() + ready2.to_wire())

        decoded = backend_decoder.read_all()
        assert decoded[1].status == TransactionStatus.IDLE
