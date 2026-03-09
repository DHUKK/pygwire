"""Integration tests for Connection-based codec and message parsing."""

from pygwire.connection import BackendConnection, FrontendConnection
from pygwire.constants import TransactionStatus
from pygwire.messages import (
    AuthenticationMD5Password,
    AuthenticationOk,
    AuthenticationSASL,
    AuthenticationSASLContinue,
    AuthenticationSASLFinal,
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
    Parse,
    ParseComplete,
    PasswordMessage,
    Query,
    ReadyForQuery,
    RowDescription,
    SASLInitialResponse,
    SASLResponse,
    SSLRequest,
    SSLResponse,
    StartupMessage,
    Sync,
)
from pygwire.state_machine import ConnectionPhase


class TestStartupSequence:
    """Integration tests for startup message sequences."""

    def test_ssl_then_startup(self):
        """Test SSL request followed by startup message."""
        client = FrontendConnection()
        server = BackendConnection()

        # Client sends SSL request
        ssl_wire = client.send(SSLRequest())
        msgs = list(server.receive(ssl_wire))
        assert len(msgs) == 1
        assert isinstance(msgs[0], SSLRequest)
        assert server.phase == ConnectionPhase.SSL_NEGOTIATION

        # Server sends SSL not-supported
        ssl_resp_wire = server.send(SSLResponse(accepted=False))
        msgs = list(client.receive(ssl_resp_wire))
        assert len(msgs) == 1
        assert isinstance(msgs[0], SSLResponse)
        assert not msgs[0].accepted

        # Client sends startup
        startup_wire = client.send(
            StartupMessage(params={"user": "testuser", "database": "testdb"})
        )
        msgs = list(server.receive(startup_wire))
        assert len(msgs) == 1
        assert isinstance(msgs[0], StartupMessage)
        assert msgs[0].params["user"] == "testuser"

    def test_startup_auth_ready_sequence(self):
        """Test full startup sequence: startup -> auth -> key data -> ready."""
        client = FrontendConnection()
        server = BackendConnection()

        # Startup
        startup_wire = client.send(StartupMessage(params={"user": "app", "database": "prod"}))
        list(server.receive(startup_wire))

        # AuthenticationOk
        auth_wire = server.send(AuthenticationOk())
        msgs = list(client.receive(auth_wire))
        assert isinstance(msgs[0], AuthenticationOk)
        assert client.phase == ConnectionPhase.INITIALIZATION

        # BackendKeyData
        key_wire = server.send(BackendKeyData(process_id=12345, secret_key=b"test"))
        msgs = list(client.receive(key_wire))
        assert isinstance(msgs[0], BackendKeyData)
        assert msgs[0].process_id == 12345

        # ReadyForQuery
        ready_wire = server.send(ReadyForQuery(status=TransactionStatus.IDLE))
        msgs = list(client.receive(ready_wire))
        assert isinstance(msgs[0], ReadyForQuery)
        assert msgs[0].status == TransactionStatus.IDLE
        assert client.phase == ConnectionPhase.READY


class TestSimpleQuerySequence:
    """Integration tests for simple query protocol sequences."""

    def _make_ready_pair(self):
        """Create client/server pair in READY state."""
        client = FrontendConnection()
        server = BackendConnection()
        startup_wire = client.send(StartupMessage(params={"user": "test"}))
        list(server.receive(startup_wire))
        auth_wire = server.send(AuthenticationOk())
        ready_wire = server.send(ReadyForQuery(status=TransactionStatus.IDLE))
        list(client.receive(auth_wire + ready_wire))
        return client, server

    def test_simple_query_flow(self):
        """Test complete simple query request and response."""
        client, server = self._make_ready_pair()

        # Client sends query
        query_wire = client.send(Query(query_string="SELECT id, name FROM users"))
        msgs = list(server.receive(query_wire))
        assert isinstance(msgs[0], Query)
        assert "users" in msgs[0].query_string

        # Server sends results
        row_desc = RowDescription(
            fields=[
                FieldDescription(name="id", type_oid=23, type_size=4),
                FieldDescription(name="name", type_oid=25, type_size=-1),
            ]
        )
        data_row = DataRow(columns=[b"1", b"Alice"])
        cmd_complete = CommandComplete(tag="SELECT 1")
        ready = ReadyForQuery(status=TransactionStatus.IDLE)

        result_wire = (
            server.send(row_desc)
            + server.send(data_row)
            + server.send(cmd_complete)
            + server.send(ready)
        )
        msgs = list(client.receive(result_wire))
        assert len(msgs) == 4
        assert isinstance(msgs[0], RowDescription)
        assert len(msgs[0].fields) == 2
        assert msgs[0].fields[0].name == "id"
        assert isinstance(msgs[1], DataRow)
        assert msgs[1].columns == [b"1", b"Alice"]
        assert isinstance(msgs[2], CommandComplete)
        assert isinstance(msgs[3], ReadyForQuery)

    def test_multiple_rows(self):
        """Test simple query with multiple result rows."""
        client, server = self._make_ready_pair()

        query_wire = client.send(Query(query_string="SELECT * FROM users"))
        list(server.receive(query_wire))

        rows = [
            DataRow(columns=[b"1", b"Alice"]),
            DataRow(columns=[b"2", b"Bob"]),
            DataRow(columns=[b"3", b"Charlie"]),
        ]
        wire = b""
        for row in rows:
            wire += server.send(row)
        wire += server.send(CommandComplete(tag="SELECT 3"))
        wire += server.send(ReadyForQuery(status=TransactionStatus.IDLE))

        msgs = list(client.receive(wire))
        data_rows = [m for m in msgs if isinstance(m, DataRow)]
        assert len(data_rows) == 3
        assert data_rows[1].columns == [b"2", b"Bob"]


class TestExtendedQuerySequence:
    """Integration tests for extended query protocol sequences."""

    def _make_ready_pair(self):
        client = FrontendConnection()
        server = BackendConnection()
        startup_wire = client.send(StartupMessage(params={"user": "test"}))
        list(server.receive(startup_wire))
        auth_wire = server.send(AuthenticationOk())
        ready_wire = server.send(ReadyForQuery(status=TransactionStatus.IDLE))
        list(client.receive(auth_wire + ready_wire))
        return client, server

    def test_parse_bind_execute_flow(self):
        """Test complete Parse/Bind/Execute/Sync flow."""
        client, server = self._make_ready_pair()

        # Client sends Parse
        parse_wire = client.send(Parse(statement="stmt1", query="SELECT $1", param_types=[23]))
        msgs = list(server.receive(parse_wire))
        assert isinstance(msgs[0], Parse)
        assert msgs[0].statement == "stmt1"

        # Server responds with ParseComplete
        pc_wire = server.send(ParseComplete())
        msgs = list(client.receive(pc_wire))
        assert isinstance(msgs[0], ParseComplete)

        # Client sends Bind
        bind_wire = client.send(Bind(portal="", statement="stmt1", param_values=[b"42"]))
        msgs = list(server.receive(bind_wire))
        assert isinstance(msgs[0], Bind)

        # Server responds with BindComplete
        bc_wire = server.send(BindComplete())
        msgs = list(client.receive(bc_wire))
        assert isinstance(msgs[0], BindComplete)

        # Client sends Execute + Sync
        exec_wire = client.send(Execute(portal="", max_rows=0))
        sync_wire = client.send(Sync())
        msgs = list(server.receive(exec_wire + sync_wire))
        assert isinstance(msgs[0], Execute)
        assert isinstance(msgs[1], Sync)

        # Server sends results + ReadyForQuery
        result_wire = (
            server.send(DataRow(columns=[b"42"]))
            + server.send(CommandComplete(tag="SELECT 1"))
            + server.send(ReadyForQuery(status=TransactionStatus.IDLE))
        )
        msgs = list(client.receive(result_wire))
        assert isinstance(msgs[0], DataRow)
        assert isinstance(msgs[1], CommandComplete)
        assert isinstance(msgs[2], ReadyForQuery)
        assert client.phase == ConnectionPhase.READY


class TestCopyProtocol:
    """Integration tests for COPY protocol."""

    def _make_ready_pair(self):
        client = FrontendConnection()
        server = BackendConnection()
        startup_wire = client.send(StartupMessage(params={"user": "test"}))
        list(server.receive(startup_wire))
        auth_wire = server.send(AuthenticationOk())
        ready_wire = server.send(ReadyForQuery(status=TransactionStatus.IDLE))
        list(client.receive(auth_wire + ready_wire))
        return client, server

    def test_copy_in_sequence(self):
        """Test COPY IN protocol flow."""
        client, server = self._make_ready_pair()

        # Client sends COPY query
        query_wire = client.send(Query(query_string="COPY test FROM STDIN"))
        list(server.receive(query_wire))

        # Server sends CopyInResponse
        cir_wire = server.send(CopyInResponse(overall_format=0, col_formats=[0, 0]))
        msgs = list(client.receive(cir_wire))
        assert isinstance(msgs[0], CopyInResponse)
        assert client.phase == ConnectionPhase.COPY_IN

        # Client sends CopyData + CopyDone
        cd1_wire = client.send(CopyData(data=b"row1\tdata1\n"))
        cd2_wire = client.send(CopyData(data=b"row2\tdata2\n"))
        done_wire = client.send(CopyDone())

        msgs = list(server.receive(cd1_wire + cd2_wire + done_wire))
        assert len(msgs) == 3
        assert isinstance(msgs[0], CopyData)
        assert isinstance(msgs[1], CopyData)
        assert isinstance(msgs[2], CopyDone)

        # Server sends CommandComplete + ReadyForQuery
        result_wire = server.send(CommandComplete(tag="COPY 2")) + server.send(
            ReadyForQuery(status=TransactionStatus.IDLE)
        )
        msgs = list(client.receive(result_wire))
        assert isinstance(msgs[0], CommandComplete)
        assert msgs[1].status == TransactionStatus.IDLE


class TestAuthenticationSequences:
    """Integration tests for various authentication flows."""

    def test_md5_auth_flow(self):
        """Test MD5 authentication flow."""
        client = FrontendConnection()
        server = BackendConnection()

        # Startup
        startup_wire = client.send(StartupMessage(params={"user": "test"}))
        list(server.receive(startup_wire))

        # Server sends AuthenticationMD5Password
        auth_wire = server.send(AuthenticationMD5Password(salt=b"\x01\x02\x03\x04"))
        msgs = list(client.receive(auth_wire))
        assert isinstance(msgs[0], AuthenticationMD5Password)
        assert msgs[0].salt == b"\x01\x02\x03\x04"

        # Client sends PasswordMessage
        pw_wire = client.send(PasswordMessage(password="md5" + "0" * 32))
        msgs = list(server.receive(pw_wire))
        assert isinstance(msgs[0], PasswordMessage)

        # Server sends AuthenticationOk + ReadyForQuery
        ok_wire = server.send(AuthenticationOk())
        ready_wire = server.send(ReadyForQuery(status=TransactionStatus.IDLE))
        msgs = list(client.receive(ok_wire + ready_wire))
        assert isinstance(msgs[0], AuthenticationOk)
        assert client.phase == ConnectionPhase.READY

    def test_sasl_auth_flow(self):
        """Test complete SASL SCRAM-SHA-256 authentication flow."""
        client = FrontendConnection()
        server = BackendConnection()

        # Startup
        startup_wire = client.send(StartupMessage(params={"user": "test"}))
        list(server.receive(startup_wire))

        # Server sends AuthenticationSASL
        sasl_wire = server.send(AuthenticationSASL(mechanisms=["SCRAM-SHA-256"]))
        msgs = list(client.receive(sasl_wire))
        assert isinstance(msgs[0], AuthenticationSASL)
        assert "SCRAM-SHA-256" in msgs[0].mechanisms
        assert client.phase == ConnectionPhase.AUTHENTICATING_SASL_INITIAL

        # Client sends SASLInitialResponse
        sir_wire = client.send(SASLInitialResponse(mechanism="SCRAM-SHA-256", data=b"client-first"))
        msgs = list(server.receive(sir_wire))
        assert isinstance(msgs[0], SASLInitialResponse)
        assert msgs[0].mechanism == "SCRAM-SHA-256"

        # Server sends AuthenticationSASLContinue
        sc_wire = server.send(AuthenticationSASLContinue(data=b"server-first"))
        msgs = list(client.receive(sc_wire))
        assert isinstance(msgs[0], AuthenticationSASLContinue)
        assert client.phase == ConnectionPhase.AUTHENTICATING_SASL_CONTINUE

        # Client sends SASLResponse
        sr_wire = client.send(SASLResponse(data=b"client-final"))
        msgs = list(server.receive(sr_wire))
        assert isinstance(msgs[0], SASLResponse)

        # Server sends SASLFinal + AuthOk + Ready
        sf_wire = server.send(AuthenticationSASLFinal(data=b"server-final"))
        ok_wire = server.send(AuthenticationOk())
        ready_wire = server.send(ReadyForQuery(status=TransactionStatus.IDLE))
        msgs = list(client.receive(sf_wire + ok_wire + ready_wire))
        assert isinstance(msgs[0], AuthenticationSASLFinal)
        assert isinstance(msgs[1], AuthenticationOk)
        assert isinstance(msgs[2], ReadyForQuery)
        assert client.phase == ConnectionPhase.READY


class TestAsyncNotifications:
    """Integration tests for asynchronous notifications."""

    def _make_ready_pair(self):
        client = FrontendConnection()
        server = BackendConnection()
        startup_wire = client.send(StartupMessage(params={"user": "test"}))
        list(server.receive(startup_wire))
        auth_wire = server.send(AuthenticationOk())
        ready_wire = server.send(ReadyForQuery(status=TransactionStatus.IDLE))
        list(client.receive(auth_wire + ready_wire))
        return client, server

    def test_notification_during_query(self):
        """Test receiving notification during query execution."""
        client, server = self._make_ready_pair()

        query_wire = client.send(Query(query_string="SELECT 1"))
        list(server.receive(query_wire))

        # Server sends data with notification interleaved
        wire = (
            server.send(DataRow(columns=[b"value1"]))
            + server.send(NotificationResponse(process_id=5678, channel="alerts", payload="alert"))
            + server.send(DataRow(columns=[b"value2"]))
            + server.send(CommandComplete(tag="SELECT 2"))
            + server.send(ReadyForQuery(status=TransactionStatus.IDLE))
        )
        msgs = list(client.receive(wire))
        assert len(msgs) == 5
        assert isinstance(msgs[0], DataRow)
        assert isinstance(msgs[1], NotificationResponse)
        assert isinstance(msgs[2], DataRow)


class TestStreamingAndBuffering:
    """Integration tests for streaming and buffer management."""

    def test_incremental_feed(self):
        """Test feeding message byte by byte."""
        conn = BackendConnection(initial_phase=ConnectionPhase.READY)
        msg = Query(query_string="SELECT 1")
        wire = msg.to_wire()

        # Feed one byte at a time
        for i, byte in enumerate(wire):
            msgs = list(conn.receive(bytes([byte])))
            if i < len(wire) - 1:
                assert msgs == []

        # Last byte should have completed the message
        assert len(msgs) == 1
        assert isinstance(msgs[0], Query)
        assert msgs[0].query_string == "SELECT 1"

    def test_partial_message_across_feeds(self):
        """Test message split across multiple feeds."""
        conn = BackendConnection(initial_phase=ConnectionPhase.READY)
        msg = Query(query_string="SELECT * FROM large_table WHERE condition = true")
        wire = msg.to_wire()

        split_point = len(wire) // 3
        msgs = list(conn.receive(wire[:split_point]))
        assert msgs == []

        msgs = list(conn.receive(wire[split_point : split_point * 2]))
        assert msgs == []

        msgs = list(conn.receive(wire[split_point * 2 :]))
        assert len(msgs) == 1
        assert isinstance(msgs[0], Query)
        assert msgs[0].query_string == msg.query_string


class TestRealWorldScenarios:
    """Integration tests simulating real-world usage patterns."""

    def test_connection_lifecycle(self):
        """Test complete connection lifecycle through Connection API."""
        client = FrontendConnection()
        server = BackendConnection()

        # Startup
        startup_wire = client.send(StartupMessage(params={"user": "app", "database": "prod"}))
        list(server.receive(startup_wire))

        # Auth + Ready
        auth_wire = server.send(AuthenticationOk())
        ready_wire = server.send(ReadyForQuery(status=TransactionStatus.IDLE))
        list(client.receive(auth_wire + ready_wire))
        assert client.phase == ConnectionPhase.READY

        # Query
        query_wire = client.send(Query(query_string="SELECT version()"))
        list(server.receive(query_wire))

        row_desc = RowDescription(fields=[FieldDescription(name="version")])
        data_row = DataRow(columns=[b"PostgreSQL 16.1"])
        cmd_complete = CommandComplete(tag="SELECT 1")
        ready = ReadyForQuery(status=TransactionStatus.IDLE)

        result_wire = (
            server.send(row_desc)
            + server.send(data_row)
            + server.send(cmd_complete)
            + server.send(ready)
        )
        msgs = list(client.receive(result_wire))
        assert len(msgs) == 4
        assert isinstance(msgs[0], RowDescription)
        assert isinstance(msgs[1], DataRow)
        assert isinstance(msgs[2], CommandComplete)
        assert isinstance(msgs[3], ReadyForQuery)
        assert client.phase == ConnectionPhase.READY

    def test_transaction_workflow(self):
        """Test transaction BEGIN/COMMIT workflow."""
        client, server = FrontendConnection(), BackendConnection()
        # Quick setup
        startup_wire = client.send(StartupMessage(params={"user": "test"}))
        list(server.receive(startup_wire))
        list(
            client.receive(
                server.send(AuthenticationOk())
                + server.send(ReadyForQuery(status=TransactionStatus.IDLE))
            )
        )

        # BEGIN
        query_wire = client.send(Query(query_string="BEGIN"))
        list(server.receive(query_wire))
        wire = server.send(CommandComplete(tag="BEGIN")) + server.send(
            ReadyForQuery(status=TransactionStatus.IN_TRANSACTION)
        )
        msgs = list(client.receive(wire))
        assert msgs[1].status == TransactionStatus.IN_TRANSACTION

        # COMMIT
        query_wire = client.send(Query(query_string="COMMIT"))
        list(server.receive(query_wire))
        wire = server.send(CommandComplete(tag="COMMIT")) + server.send(
            ReadyForQuery(status=TransactionStatus.IDLE)
        )
        msgs = list(client.receive(wire))
        assert msgs[1].status == TransactionStatus.IDLE
