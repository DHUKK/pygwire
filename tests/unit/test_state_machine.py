"""Tests for the PostgreSQL wire protocol state machine."""

import pytest

from pygwire.constants import TransactionStatus
from pygwire.messages import (
    AuthenticationCleartextPassword,
    AuthenticationMD5Password,
    AuthenticationOk,
    AuthenticationSASL,
    AuthenticationSASLContinue,
    AuthenticationSASLFinal,
    BackendKeyData,
    Bind,
    BindComplete,
    Close,
    CloseComplete,
    CommandComplete,
    CopyData,
    CopyDone,
    CopyFail,
    CopyInResponse,
    CopyOutResponse,
    DataRow,
    Describe,
    EmptyQueryResponse,
    ErrorResponse,
    Execute,
    FunctionCall,
    FunctionCallResponse,
    NoticeResponse,
    NotificationResponse,
    ParameterStatus,
    Parse,
    ParseComplete,
    PasswordMessage,
    Query,
    ReadyForQuery,
    RowDescription,
    SASLInitialResponse,
    SASLResponse,
    SSLRequest,
    StartupMessage,
    Sync,
    Terminate,
)
from pygwire.state_machine import (
    BackendStateMachine,
    ConnectionPhase,
    FrontendStateMachine,
    StateMachineError,
)


class TestFrontendStateMachine:
    """Tests for FrontendStateMachine."""

    def test_initial_state(self):
        """Test initial state is STARTUP."""
        sm = FrontendStateMachine()
        assert sm.phase == ConnectionPhase.STARTUP
        assert not sm.is_ready
        assert sm.is_active

    def test_startup_success_flow(self):
        """Test successful startup with cleartext auth."""
        sm = FrontendStateMachine()

        # Send StartupMessage
        sm.send(StartupMessage(params={"user": "test"}))
        assert sm.phase == ConnectionPhase.STARTUP

        # Receive Authentication request
        sm.receive(AuthenticationCleartextPassword())
        assert sm.phase == ConnectionPhase.AUTHENTICATING

        # Send password
        sm.send(PasswordMessage(password="secret"))
        assert sm.phase == ConnectionPhase.AUTHENTICATING

        # Receive AuthenticationOk
        sm.receive(AuthenticationOk())
        assert sm.phase == ConnectionPhase.INITIALIZATION

        # Receive BackendKeyData
        sm.receive(BackendKeyData(process_id=1234, secret_key=b"secret"))
        assert sm.phase == ConnectionPhase.INITIALIZATION

        # Receive ReadyForQuery
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY
        assert sm.is_ready
        assert sm.is_active

    def test_startup_md5_auth_flow(self):
        """Test startup with MD5 authentication."""
        sm = FrontendStateMachine()

        sm.send(StartupMessage(params={"user": "test"}))
        sm.receive(AuthenticationMD5Password(salt=b"\x00\x01\x02\x03"))
        assert sm.phase == ConnectionPhase.AUTHENTICATING

        sm.send(PasswordMessage(password="hashed"))
        sm.receive(AuthenticationOk())
        assert sm.phase == ConnectionPhase.INITIALIZATION

        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY

    def test_startup_sasl_auth_flow(self):
        """Test startup with SASL authentication."""
        sm = FrontendStateMachine()

        sm.send(StartupMessage(params={"user": "test"}))
        sm.receive(AuthenticationSASL(mechanisms=["SCRAM-SHA-256"]))
        assert sm.phase == ConnectionPhase.AUTHENTICATING_SASL_INITIAL

        sm.send(SASLInitialResponse(mechanism="SCRAM-SHA-256", data=b"client-first"))
        assert sm.phase == ConnectionPhase.AUTHENTICATING_SASL_INITIAL

        sm.receive(AuthenticationSASLContinue(data=b"server-first"))
        assert sm.phase == ConnectionPhase.AUTHENTICATING_SASL_CONTINUE

        sm.send(SASLResponse(data=b"client-final"))
        sm.receive(AuthenticationSASLFinal(data=b"server-final"))
        assert sm.phase == ConnectionPhase.AUTHENTICATING

        sm.receive(AuthenticationOk())
        assert sm.phase == ConnectionPhase.INITIALIZATION

        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY

    def test_ssl_request_flow(self):
        """Test SSL request at startup."""
        sm = FrontendStateMachine()

        sm.send(SSLRequest())
        assert sm.phase == ConnectionPhase.SSL_NEGOTIATION

        # After SSL negotiation (single-byte response, not a message),
        # send StartupMessage
        sm.send(StartupMessage(params={"user": "test"}))
        assert sm.phase == ConnectionPhase.STARTUP

    def test_simple_query_flow(self):
        """Test simple query protocol."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        # Send query
        sm.send(Query(query_string="SELECT 1"))
        assert sm.phase == ConnectionPhase.SIMPLE_QUERY

        # Receive results
        sm.receive(RowDescription(fields=[]))
        sm.receive(DataRow(columns=[b"1"]))
        sm.receive(CommandComplete(tag="SELECT 1"))
        assert sm.phase == ConnectionPhase.SIMPLE_QUERY

        # Receive ReadyForQuery
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY

    def test_empty_query(self):
        """Test empty query response."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        sm.send(Query(query_string=""))
        sm.receive(EmptyQueryResponse())
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY

    def test_extended_query_flow(self):
        """Test extended query protocol."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        # Parse
        sm.send(Parse(statement="stmt1", query="SELECT $1", param_types=[23]))
        assert sm.phase == ConnectionPhase.EXTENDED_QUERY
        sm.receive(ParseComplete())

        # Bind
        sm.send(Bind(portal="", statement="stmt1", param_values=[b"42"]))
        sm.receive(BindComplete())

        # Describe
        sm.send(Describe(kind="P", name=""))
        sm.receive(RowDescription(fields=[]))

        # Execute
        sm.send(Execute(portal="", max_rows=0))
        sm.receive(DataRow(columns=[b"42"]))
        sm.receive(CommandComplete(tag="SELECT 1"))

        # Sync
        sm.send(Sync())
        assert sm.phase == ConnectionPhase.EXTENDED_QUERY

        # ReadyForQuery ends extended query
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY

    def test_extended_query_close(self):
        """Test Close in extended query protocol."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        sm.send(Parse(statement="stmt1", query="SELECT 1"))
        sm.receive(ParseComplete())

        sm.send(Close(kind="S", name="stmt1"))
        sm.receive(CloseComplete())

        sm.send(Sync())
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY

    def test_copy_in_flow(self):
        """Test COPY IN protocol."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        sm.send(Query(query_string="COPY table FROM STDIN"))
        sm.receive(CopyInResponse(overall_format=0, col_formats=[]))
        assert sm.phase == ConnectionPhase.COPY_IN

        # Send copy data
        sm.send(CopyData(data=b"row1\n"))
        sm.send(CopyData(data=b"row2\n"))
        assert sm.phase == ConnectionPhase.COPY_IN

        # Send CopyDone
        sm.send(CopyDone())
        assert sm.phase == ConnectionPhase.SIMPLE_QUERY

        sm.receive(CommandComplete(tag="COPY 2"))
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY

    def test_copy_in_fail(self):
        """Test COPY IN with failure."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        sm.send(Query(query_string="COPY table FROM STDIN"))
        sm.receive(CopyInResponse(overall_format=0, col_formats=[]))

        sm.send(CopyFail(error_message="user abort"))
        assert sm.phase == ConnectionPhase.SIMPLE_QUERY

        sm.receive(ErrorResponse(fields={"S": "ERROR", "M": "COPY aborted"}))
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY

    def test_copy_out_flow(self):
        """Test COPY OUT protocol."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        sm.send(Query(query_string="COPY table TO STDOUT"))
        sm.receive(CopyOutResponse(overall_format=0, col_formats=[]))
        assert sm.phase == ConnectionPhase.COPY_OUT

        # Receive copy data
        sm.receive(CopyData(data=b"row1\n"))
        sm.receive(CopyData(data=b"row2\n"))
        sm.receive(CopyDone())
        assert sm.phase == ConnectionPhase.SIMPLE_QUERY

        sm.receive(CommandComplete(tag="COPY 2"))
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY

    def test_function_call_flow(self):
        """Test function call protocol."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        sm.send(FunctionCall(function_oid=123, arguments=[b"arg1"]))
        assert sm.phase == ConnectionPhase.FUNCTION_CALL

        sm.receive(FunctionCallResponse(result=b"result"))
        assert sm.phase == ConnectionPhase.SIMPLE_QUERY

        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY

    def test_terminate_from_ready(self):
        """Test Terminate from READY state."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        sm.send(Terminate())
        assert sm.phase == ConnectionPhase.TERMINATED
        assert not sm.is_active

    def test_terminate_from_startup(self):
        """Test Terminate during startup."""
        sm = FrontendStateMachine()
        sm.send(Terminate())
        assert sm.phase == ConnectionPhase.TERMINATED

    def test_error_during_startup_fails(self):
        """Test ErrorResponse during startup causes FAILED state."""
        sm = FrontendStateMachine()

        sm.send(StartupMessage(params={"user": "test"}))
        sm.receive(ErrorResponse(fields={"S": "FATAL", "M": "invalid user"}))
        assert sm.phase == ConnectionPhase.FAILED
        assert not sm.is_active

    def test_error_during_auth_fails(self):
        """Test ErrorResponse during authentication causes FAILED state."""
        sm = FrontendStateMachine()

        sm.send(StartupMessage(params={"user": "test"}))
        sm.receive(AuthenticationCleartextPassword())
        sm.send(PasswordMessage(password="wrong"))
        sm.receive(ErrorResponse(fields={"S": "FATAL", "M": "auth failed"}))
        assert sm.phase == ConnectionPhase.FAILED

    def test_error_during_query_doesnt_fail(self):
        """Test ErrorResponse during query doesn't fail connection."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        sm.send(Query(query_string="SELECT * FROM nonexistent"))
        sm.receive(ErrorResponse(fields={"S": "ERROR", "M": "table not found"}))
        assert sm.phase == ConnectionPhase.SIMPLE_QUERY

        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY
        assert sm.is_active

    def test_notice_response_anytime(self):
        """Test NoticeResponse can arrive in any phase."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        # In READY
        sm.receive(NoticeResponse(fields={"S": "NOTICE", "M": "test"}))
        assert sm.phase == ConnectionPhase.READY

        # In SIMPLE_QUERY
        sm.send(Query(query_string="SELECT 1"))
        sm.receive(NoticeResponse(fields={"S": "NOTICE", "M": "test"}))
        assert sm.phase == ConnectionPhase.SIMPLE_QUERY

        sm.receive(EmptyQueryResponse())
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))

    def test_parameter_status_anytime(self):
        """Test ParameterStatus can arrive in any phase."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        sm.receive(ParameterStatus(name="TimeZone", value="UTC"))
        assert sm.phase == ConnectionPhase.READY

    def test_notification_response_anytime(self):
        """Test NotificationResponse can arrive in any phase."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        sm.receive(NotificationResponse(process_id=123, channel="test", payload="data"))
        assert sm.phase == ConnectionPhase.READY

    def test_invalid_message_in_startup(self):
        """Test sending invalid message in STARTUP phase."""
        sm = FrontendStateMachine()

        with pytest.raises(StateMachineError, match="Cannot send Query in phase STARTUP"):
            sm.send(Query(query_string="SELECT 1"))

    def test_invalid_message_in_ready(self):
        """Test receiving invalid message in READY phase."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        with pytest.raises(StateMachineError, match="Cannot receive DataRow in phase READY"):
            sm.receive(DataRow(columns=[b"1"]))

    def test_invalid_message_in_simple_query(self):
        """Test sending invalid message during simple query."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        sm.send(Query(query_string="SELECT 1"))

        # Simple query protocol does not support pipelining at all
        with pytest.raises(StateMachineError, match="Cannot send Query in phase SIMPLE_QUERY"):
            sm.send(Query(query_string="SELECT 2"))

    def test_invalid_message_in_copy_out(self):
        """Test sending data during COPY OUT (backend sends data)."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        sm.send(Query(query_string="COPY table TO STDOUT"))
        sm.receive(CopyOutResponse(overall_format=0, col_formats=[]))

        with pytest.raises(StateMachineError, match="Cannot send CopyData in phase COPY_OUT"):
            sm.send(CopyData(data=b"invalid"))

    def test_cannot_send_after_terminate(self):
        """Test cannot send messages after Terminate."""
        sm = FrontendStateMachine()
        sm.send(Terminate())

        with pytest.raises(StateMachineError, match="Cannot send Terminate in phase TERMINATED"):
            sm.send(Terminate())

    def test_cannot_receive_after_failed(self):
        """Test cannot receive messages after FAILED."""
        sm = FrontendStateMachine()
        sm.send(StartupMessage(params={"user": "test"}))
        sm.receive(ErrorResponse(fields={"S": "FATAL", "M": "error"}))

        with pytest.raises(StateMachineError):
            sm.receive(AuthenticationOk())

    def _do_startup(self, sm: FrontendStateMachine) -> None:
        """Helper to complete startup sequence."""
        sm.send(StartupMessage(params={"user": "test"}))
        sm.receive(AuthenticationOk())
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))


class TestBackendStateMachine:
    """Tests for BackendStateMachine."""

    def test_initial_state(self):
        """Test initial state is STARTUP."""
        sm = BackendStateMachine()
        assert sm.phase == ConnectionPhase.STARTUP
        assert not sm.is_ready
        assert sm.is_active

    def test_startup_success_flow(self):
        """Test successful startup from backend perspective."""
        sm = BackendStateMachine()

        # Receive StartupMessage
        sm.receive(StartupMessage(params={"user": "test"}))
        assert sm.phase == ConnectionPhase.STARTUP

        # Send Authentication request
        sm.send(AuthenticationCleartextPassword())
        assert sm.phase == ConnectionPhase.AUTHENTICATING

        # Receive password
        sm.receive(PasswordMessage(password="secret"))
        assert sm.phase == ConnectionPhase.AUTHENTICATING

        # Send AuthenticationOk
        sm.send(AuthenticationOk())
        assert sm.phase == ConnectionPhase.INITIALIZATION

        # Send BackendKeyData
        sm.send(BackendKeyData(process_id=1234, secret_key=b"secret"))
        assert sm.phase == ConnectionPhase.INITIALIZATION

        # Send ReadyForQuery
        sm.send(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY
        assert sm.is_ready

    def test_simple_query_flow(self):
        """Test simple query from backend perspective."""
        sm = BackendStateMachine()
        self._do_startup(sm)

        # Receive query
        sm.receive(Query(query_string="SELECT 1"))
        assert sm.phase == ConnectionPhase.SIMPLE_QUERY

        # Send results
        sm.send(RowDescription(fields=[]))
        sm.send(DataRow(columns=[b"1"]))
        sm.send(CommandComplete(tag="SELECT 1"))
        assert sm.phase == ConnectionPhase.SIMPLE_QUERY

        # Send ReadyForQuery
        sm.send(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY

    def test_extended_query_flow(self):
        """Test extended query from backend perspective."""
        sm = BackendStateMachine()
        self._do_startup(sm)

        # Receive Parse
        sm.receive(Parse(statement="stmt1", query="SELECT $1", param_types=[23]))
        assert sm.phase == ConnectionPhase.EXTENDED_QUERY
        sm.send(ParseComplete())

        # Receive Bind
        sm.receive(Bind(portal="", statement="stmt1", param_values=[b"42"]))
        sm.send(BindComplete())

        # Receive Execute
        sm.receive(Execute(portal="", max_rows=0))
        sm.send(DataRow(columns=[b"42"]))
        sm.send(CommandComplete(tag="SELECT 1"))

        # Receive Sync
        sm.receive(Sync())
        assert sm.phase == ConnectionPhase.EXTENDED_QUERY

        # Send ReadyForQuery
        sm.send(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY

    def test_copy_in_flow(self):
        """Test COPY IN from backend perspective."""
        sm = BackendStateMachine()
        self._do_startup(sm)

        sm.receive(Query(query_string="COPY table FROM STDIN"))
        sm.send(CopyInResponse(overall_format=0, col_formats=[]))
        assert sm.phase == ConnectionPhase.COPY_IN

        # Receive copy data
        sm.receive(CopyData(data=b"row1\n"))
        sm.receive(CopyData(data=b"row2\n"))
        sm.receive(CopyDone())
        assert sm.phase == ConnectionPhase.SIMPLE_QUERY

        sm.send(CommandComplete(tag="COPY 2"))
        sm.send(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY

    def test_copy_out_flow(self):
        """Test COPY OUT from backend perspective."""
        sm = BackendStateMachine()
        self._do_startup(sm)

        sm.receive(Query(query_string="COPY table TO STDOUT"))
        sm.send(CopyOutResponse(overall_format=0, col_formats=[]))
        assert sm.phase == ConnectionPhase.COPY_OUT

        # Send copy data
        sm.send(CopyData(data=b"row1\n"))
        sm.send(CopyData(data=b"row2\n"))
        sm.send(CopyDone())
        assert sm.phase == ConnectionPhase.SIMPLE_QUERY

        sm.send(CommandComplete(tag="COPY 2"))
        sm.send(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY

    def test_terminate_received(self):
        """Test receiving Terminate."""
        sm = BackendStateMachine()
        self._do_startup(sm)

        sm.receive(Terminate())
        assert sm.phase == ConnectionPhase.TERMINATED
        assert not sm.is_active

    def test_error_response_sent_during_query(self):
        """Test sending ErrorResponse during query."""
        sm = BackendStateMachine()
        self._do_startup(sm)

        sm.receive(Query(query_string="SELECT * FROM bad"))
        sm.send(ErrorResponse(fields={"S": "ERROR", "M": "error"}))
        assert sm.phase == ConnectionPhase.SIMPLE_QUERY

        sm.send(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY
        assert sm.is_active

    def test_notice_parameter_status_anytime(self):
        """Test backend can send notice/parameter status anytime."""
        sm = BackendStateMachine()
        self._do_startup(sm)

        sm.send(NoticeResponse(fields={"S": "NOTICE", "M": "test"}))
        sm.send(ParameterStatus(name="TimeZone", value="UTC"))
        sm.send(NotificationResponse(process_id=123, channel="test", payload="data"))
        assert sm.phase == ConnectionPhase.READY

    def test_invalid_receive_in_startup(self):
        """Test receiving invalid message in STARTUP."""
        sm = BackendStateMachine()

        with pytest.raises(StateMachineError):
            sm.receive(Query(query_string="SELECT 1"))

    def test_invalid_send_in_ready(self):
        """Test sending query results when idle."""
        sm = BackendStateMachine()
        self._do_startup(sm)

        with pytest.raises(StateMachineError):
            sm.send(DataRow(columns=[b"1"]))

    def _do_startup(self, sm: BackendStateMachine) -> None:
        """Helper to complete startup sequence."""
        sm.receive(StartupMessage(params={"user": "test"}))
        sm.send(AuthenticationOk())
        sm.send(ReadyForQuery(status=TransactionStatus.IDLE))


class TestPipelining:
    """Tests for extended query pipelining."""

    def test_two_pipelined_batches(self):
        """Test two pipelined extended query batches."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        # First batch: Parse + Bind + Execute + Sync
        sm.send(Parse(statement="stmt1", query="SELECT $1"))
        assert sm.phase == ConnectionPhase.EXTENDED_QUERY
        assert sm.pending_syncs == 1

        sm.send(Bind(portal="", statement="stmt1", param_values=[b"1"]))
        sm.send(Execute(portal="", max_rows=0))
        sm.send(Sync())

        # Second batch: Parse + Bind + Execute + Sync (pipelined without waiting for first batch)
        sm.send(Parse(statement="stmt2", query="SELECT $1"))
        assert sm.pending_syncs == 2  # Now tracking two batches

        sm.send(Bind(portal="", statement="stmt2", param_values=[b"2"]))
        sm.send(Execute(portal="", max_rows=0))
        sm.send(Sync())

        # Receive responses for first batch
        sm.receive(ParseComplete())
        sm.receive(BindComplete())
        sm.receive(DataRow(columns=[b"1"]))
        sm.receive(CommandComplete(tag="SELECT 1"))
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))

        # Still in EXTENDED_QUERY because second batch is pending
        assert sm.phase == ConnectionPhase.EXTENDED_QUERY
        assert sm.pending_syncs == 1

        # Receive responses for second batch
        sm.receive(ParseComplete())
        sm.receive(BindComplete())
        sm.receive(DataRow(columns=[b"2"]))
        sm.receive(CommandComplete(tag="SELECT 1"))
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))

        # Now back to READY
        assert sm.phase == ConnectionPhase.READY
        assert sm.pending_syncs == 0

    def test_pipelining_disabled(self):
        """Test that pipelining always works (pipelining is always enabled)."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        # First batch
        sm.send(Parse(statement="stmt1", query="SELECT 1"))
        sm.send(Bind(portal="", statement="stmt1"))
        sm.send(Execute(portal="", max_rows=0))
        sm.send(Sync())

        # Second batch should succeed (pipelining is always enabled)
        sm.send(Parse(statement="stmt2", query="SELECT 2"))
        assert sm.pending_syncs == 2

    def test_sync_before_batch(self):
        """Test sending Sync before starting a batch."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        # Send standalone Sync from READY
        sm.send(Sync())
        assert sm.phase == ConnectionPhase.EXTENDED_QUERY
        assert sm.pending_syncs == 1

        # Receive ReadyForQuery
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY
        assert sm.pending_syncs == 0

    def test_multiple_syncs_in_batch(self):
        """Test multiple Sync messages in a single batch."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        # Parse + Sync + Parse + Sync
        sm.send(Parse(statement="stmt1", query="SELECT 1"))
        sm.send(Sync())
        assert sm.pending_syncs == 1

        sm.send(Parse(statement="stmt2", query="SELECT 2"))
        sm.send(Sync())
        assert sm.pending_syncs == 2

        # Receive first batch response
        sm.receive(ParseComplete())
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.pending_syncs == 1

        # Receive second batch response
        sm.receive(ParseComplete())
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY
        assert sm.pending_syncs == 0

    def test_pending_syncs_counter(self):
        """Test that pending_syncs counter increments and decrements correctly."""
        sm = FrontendStateMachine()
        self._do_startup(sm)

        assert sm.pending_syncs == 0

        # Send three pipelined batches
        for i in range(3):
            sm.send(Parse(statement=f"stmt{i}", query="SELECT 1"))
            sm.send(Sync())
            assert sm.pending_syncs == i + 1

        # Process responses one by one
        for i in range(3):
            sm.receive(ParseComplete())
            sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
            expected_pending = 2 - i
            assert sm.pending_syncs == expected_pending

        assert sm.phase == ConnectionPhase.READY
        assert sm.pending_syncs == 0

    def test_backend_pipelining(self):
        """Test pipelining from backend perspective."""
        sm = BackendStateMachine()
        self._do_startup(sm)

        # Receive two pipelined batches
        sm.receive(Parse(statement="stmt1", query="SELECT 1"))
        sm.receive(Sync())
        assert sm.pending_syncs == 1

        sm.receive(Parse(statement="stmt2", query="SELECT 2"))
        sm.receive(Sync())
        assert sm.pending_syncs == 2

        # Send responses for first batch
        sm.send(ParseComplete())
        sm.send(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.pending_syncs == 1

        # Send responses for second batch
        sm.send(ParseComplete())
        sm.send(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == ConnectionPhase.READY
        assert sm.pending_syncs == 0

    def _do_startup(self, sm):
        """Helper to complete startup sequence."""
        if isinstance(sm, FrontendStateMachine):
            sm.send(StartupMessage(params={"user": "test"}))
            sm.receive(AuthenticationOk())
            sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        else:  # BackendStateMachine
            sm.receive(StartupMessage(params={"user": "test"}))
            sm.send(AuthenticationOk())
            sm.send(ReadyForQuery(status=TransactionStatus.IDLE))


class TestConnectionPhaseEnum:
    """Tests for ConnectionPhase enum."""

    def test_all_phases_defined(self):
        """Test all expected phases are defined."""
        expected_phases = [
            "STARTUP",
            "SSL_NEGOTIATION",
            "GSS_NEGOTIATION",
            "AUTHENTICATING",
            "INITIALIZATION",
            "READY",
            "SIMPLE_QUERY",
            "EXTENDED_QUERY",
            "COPY_IN",
            "COPY_OUT",
            "COPY_BOTH",
            "FUNCTION_CALL",
            "TERMINATED",
            "FAILED",
        ]
        for phase_name in expected_phases:
            assert hasattr(ConnectionPhase, phase_name)

    def test_phase_enum_values(self):
        """Test phase enum values are unique."""
        phases = list(ConnectionPhase)
        assert len(phases) == len(set(phases))
