"""Unit tests for pygwire.state_machine.

Tests each component in isolation: _State dataclass, transition action classes,
_StateMachineCore._process rule matching, error/hint generation, and the
FrontendStateMachine / BackendStateMachine public API.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from pygwire.constants import ConnectionPhase, TransactionStatus
from pygwire.exceptions import StateMachineError
from pygwire.messages import (
    AuthenticationCleartextPassword,
    AuthenticationGSSContinue,
    AuthenticationMD5Password,
    AuthenticationOk,
    AuthenticationSASL,
    AuthenticationSASLContinue,
    AuthenticationSASLFinal,
    BackendKeyData,
    Bind,
    BindComplete,
    CancelRequest,
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
    Flush,
    FunctionCall,
    FunctionCallResponse,
    GSSEncRequest,
    GSSResponse,
    NegotiateProtocolVersion,
    NoData,
    NoticeResponse,
    NotificationResponse,
    ParameterDescription,
    ParameterStatus,
    Parse,
    ParseComplete,
    PasswordMessage,
    PortalSuspended,
    Query,
    ReadyForQuery,
    RowDescription,
    SASLInitialResponse,
    SASLResponse,
    SSLRequest,
    SSLResponse,
    StartupMessage,
    Sync,
    Terminate,
)
from pygwire.state_machine import (
    BackendStateMachine,
    FrontendStateMachine,
    MessageAction,
    _generate_hints,
    _State,
    _StateMachineCore,
    _Stay,
    _Transition,
    copy_done,
    ext_continue,
    ext_rfq,
    ext_start,
    ext_sync,
    stay,
    sync_from_ready,
    to,
)

_P = ConnectionPhase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_core(phase: ConnectionPhase = _P.STARTUP, **state_kwargs) -> _StateMachineCore:
    """Build a _StateMachineCore with a specific initial _State."""
    core = _StateMachineCore(phase=phase)
    if state_kwargs:
        core._state = replace(core._state, **state_kwargs)
    return core


# ---------------------------------------------------------------------------
# _State dataclass
# ---------------------------------------------------------------------------


class TestState:
    def test_defaults(self):
        s = _State(phase=_P.STARTUP)
        assert s.phase == _P.STARTUP
        assert s.in_extended_batch is False
        assert s.pending_syncs == 0

    def test_frozen(self):
        s = _State(phase=_P.STARTUP)
        with pytest.raises(AttributeError):
            s.phase = _P.READY  # type: ignore[misc]

    def test_replace_creates_new_instance(self):
        s1 = _State(phase=_P.STARTUP)
        s2 = replace(s1, phase=_P.READY)
        assert s1.phase == _P.STARTUP
        assert s2.phase == _P.READY
        assert s1 is not s2


# ---------------------------------------------------------------------------
# Transition action classes (unit-tested against _StateMachineCore)
# ---------------------------------------------------------------------------


class TestTransition:
    def test_transition_changes_phase(self):
        core = _make_core(_P.STARTUP)
        _Transition(_P.READY)(core)
        assert core.phase == _P.READY

    def test_to_helper_returns_transition(self):
        t = to(_P.AUTHENTICATING)
        assert isinstance(t, _Transition)
        core = _make_core(_P.STARTUP)
        t(core)
        assert core.phase == _P.AUTHENTICATING


class TestStay:
    def test_stay_does_not_change_phase(self):
        core = _make_core(_P.READY)
        _Stay()(core)
        assert core.phase == _P.READY

    def test_stay_preserves_all_state(self):
        core = _make_core(_P.EXTENDED_QUERY, in_extended_batch=True, pending_syncs=3)
        state_before = core._state
        stay(core)
        assert core._state is state_before


class TestExtStart:
    def test_transitions_to_extended_query(self):
        core = _make_core(_P.READY)
        ext_start(core)
        assert core.phase == _P.EXTENDED_QUERY

    def test_sets_in_extended_batch(self):
        core = _make_core(_P.READY)
        ext_start(core)
        assert core._state.in_extended_batch is True

    def test_increments_pending_syncs(self):
        core = _make_core(_P.READY)
        ext_start(core)
        assert core._state.pending_syncs == 1

    def test_increments_from_existing_pending_syncs(self):
        core = _make_core(_P.READY, pending_syncs=2)
        ext_start(core)
        assert core._state.pending_syncs == 3


class TestExtContinue:
    def test_starts_new_batch_when_not_in_batch(self):
        core = _make_core(_P.EXTENDED_QUERY, in_extended_batch=False, pending_syncs=1)
        ext_continue(core)
        assert core._state.in_extended_batch is True
        assert core._state.pending_syncs == 2

    def test_noop_when_already_in_batch(self):
        core = _make_core(_P.EXTENDED_QUERY, in_extended_batch=True, pending_syncs=1)
        state_before = core._state
        ext_continue(core)
        assert core._state is state_before


class TestExtSync:
    def test_ends_batch_when_in_batch(self):
        core = _make_core(_P.EXTENDED_QUERY, in_extended_batch=True, pending_syncs=1)
        ext_sync(core)
        assert core._state.in_extended_batch is False
        assert core._state.pending_syncs == 1  # not changed

    def test_adds_sync_point_when_not_in_batch(self):
        core = _make_core(_P.EXTENDED_QUERY, in_extended_batch=False, pending_syncs=1)
        ext_sync(core)
        assert core._state.pending_syncs == 2


class TestExtReadyForQuery:
    def test_decrements_pending_syncs(self):
        core = _make_core(_P.EXTENDED_QUERY, pending_syncs=3)
        ext_rfq(core)
        assert core._state.pending_syncs == 2
        assert core.phase == _P.EXTENDED_QUERY

    def test_returns_to_ready_when_last_sync(self):
        core = _make_core(_P.EXTENDED_QUERY, pending_syncs=1)
        ext_rfq(core)
        assert core.phase == _P.READY
        assert core._state.pending_syncs == 0
        assert core._state.in_extended_batch is False

    def test_returns_to_ready_when_zero_pending(self):
        """Edge case: pending_syncs was 0 (shouldn't normally happen), goes to READY."""
        core = _make_core(_P.EXTENDED_QUERY, pending_syncs=0)
        ext_rfq(core)
        assert core.phase == _P.READY
        assert core._state.pending_syncs == 0


class TestCopyDone:
    def test_transitions_to_simple_query(self):
        core = _make_core(_P.COPY_IN)
        copy_done(core)
        assert core.phase == _P.SIMPLE_QUERY

    def test_from_copy_out(self):
        core = _make_core(_P.COPY_OUT)
        copy_done(core)
        assert core.phase == _P.SIMPLE_QUERY


class TestSyncFromReady:
    def test_transitions_to_extended_query(self):
        core = _make_core(_P.READY)
        sync_from_ready(core)
        assert core.phase == _P.EXTENDED_QUERY

    def test_increments_pending_syncs(self):
        core = _make_core(_P.READY)
        sync_from_ready(core)
        assert core._state.pending_syncs == 1

    def test_sets_in_extended_batch_false(self):
        core = _make_core(_P.READY)
        sync_from_ready(core)
        assert core._state.in_extended_batch is False


# ---------------------------------------------------------------------------
# _StateMachineCore properties
# ---------------------------------------------------------------------------


class TestStateMachineCoreProperties:
    def test_phase(self):
        core = _make_core(_P.READY)
        assert core.phase == _P.READY

    def test_is_ready_true(self):
        core = _make_core(_P.READY)
        assert core.is_ready is True

    def test_is_ready_false(self):
        core = _make_core(_P.STARTUP)
        assert core.is_ready is False

    def test_is_active_true(self):
        core = _make_core(_P.READY)
        assert core.is_active is True

    def test_is_active_false_terminated(self):
        core = _make_core(_P.TERMINATED)
        assert core.is_active is False

    def test_is_active_false_failed(self):
        core = _make_core(_P.FAILED)
        assert core.is_active is False

    def test_pending_syncs(self):
        core = _make_core(_P.EXTENDED_QUERY, pending_syncs=5)
        assert core.pending_syncs == 5

    def test_default_pending_syncs(self):
        core = _make_core(_P.STARTUP)
        assert core.pending_syncs == 0


# ---------------------------------------------------------------------------
# _StateMachineCore._process — rule matching
# ---------------------------------------------------------------------------


class TestProcessRuleMatching:
    def test_matches_first_matching_rule(self):
        sm = FrontendStateMachine()
        sm.send(SSLRequest())
        assert sm.phase == _P.SSL_NEGOTIATION

    def test_raises_when_no_rule_for_phase(self):
        sm = FrontendStateMachine(phase=_P.TERMINATED)
        with pytest.raises(StateMachineError, match="Cannot send"):
            sm.send(Terminate())

    def test_raises_when_no_matching_message_type(self):
        sm = FrontendStateMachine()
        with pytest.raises(StateMachineError, match="Cannot send Query in phase STARTUP"):
            sm.send(Query(query_string="SELECT 1"))

    def test_error_includes_hint(self):
        sm = FrontendStateMachine()
        with pytest.raises(StateMachineError, match="expected"):
            sm.send(Query(query_string="SELECT 1"))

    def test_isinstance_matching_with_tuple_of_types(self):
        """Rules with multiple message types in a tuple should match any of them."""
        sm = FrontendStateMachine(phase=_P.READY)
        sm.send(Parse(statement="s", query="SELECT 1"))
        assert sm.phase == _P.EXTENDED_QUERY

        sm2 = FrontendStateMachine(phase=_P.READY)
        sm2.send(Bind(portal="", statement="s"))
        assert sm2.phase == _P.EXTENDED_QUERY


# ---------------------------------------------------------------------------
# _generate_hints
# ---------------------------------------------------------------------------


class TestGenerateHints:
    def test_single_message_type(self):
        rules = {_P.STARTUP: [((Query,), stay)]}
        hints = _generate_hints(rules)
        assert hints[_P.STARTUP] == "expected Query"

    def test_multiple_message_types(self):
        rules = {_P.STARTUP: [((Query, Parse), stay)]}
        hints = _generate_hints(rules)
        assert hints[_P.STARTUP] == "expected Query, or Parse"

    def test_multiple_rules(self):
        rules = {_P.STARTUP: [((Query,), stay), ((Terminate,), stay)]}
        hints = _generate_hints(rules)
        assert hints[_P.STARTUP] == "expected Query, or Terminate"

    def test_empty_rules(self):
        rules = {_P.STARTUP: []}
        hints = _generate_hints(rules)
        assert _P.STARTUP not in hints

    def test_three_plus_types(self):
        rules = {_P.STARTUP: [((Query, Parse, Bind), stay)]}
        hints = _generate_hints(rules)
        assert hints[_P.STARTUP] == "expected Query, Parse, or Bind"


# ---------------------------------------------------------------------------
# MessageAction enum
# ---------------------------------------------------------------------------


class TestMessageAction:
    def test_send_value(self):
        assert MessageAction.SEND == "send"

    def test_receive_value(self):
        assert MessageAction.RECEIVE == "receive"


# ---------------------------------------------------------------------------
# FrontendStateMachine — send/receive routing
# ---------------------------------------------------------------------------


class TestFrontendStateMachine:
    def test_initial_phase_default(self):
        sm = FrontendStateMachine()
        assert sm.phase == _P.STARTUP

    def test_initial_phase_custom(self):
        sm = FrontendStateMachine(phase=_P.READY)
        assert sm.phase == _P.READY

    def test_send_routes_to_frontend_rules(self):
        sm = FrontendStateMachine()
        sm.send(StartupMessage(params={"user": "test"}))
        assert sm.phase == _P.STARTUP

    def test_receive_routes_to_backend_rules(self):
        sm = FrontendStateMachine()
        sm.send(StartupMessage(params={"user": "test"}))
        sm.receive(AuthenticationOk())
        assert sm.phase == _P.INITIALIZATION

    def test_send_invalid_raises_with_send_action(self):
        sm = FrontendStateMachine()
        with pytest.raises(StateMachineError, match="Cannot send"):
            sm.send(Query(query_string="SELECT 1"))

    def test_receive_invalid_raises_with_receive_action(self):
        sm = FrontendStateMachine(phase=_P.READY)
        with pytest.raises(StateMachineError, match="Cannot receive"):
            sm.receive(DataRow(columns=[b"1"]))


# ---------------------------------------------------------------------------
# BackendStateMachine — send/receive routing
# ---------------------------------------------------------------------------


class TestBackendStateMachine:
    def test_initial_phase_default(self):
        sm = BackendStateMachine()
        assert sm.phase == _P.STARTUP

    def test_initial_phase_custom(self):
        sm = BackendStateMachine(phase=_P.READY)
        assert sm.phase == _P.READY

    def test_receive_routes_to_frontend_rules(self):
        sm = BackendStateMachine()
        sm.receive(StartupMessage(params={"user": "test"}))
        assert sm.phase == _P.STARTUP

    def test_send_routes_to_backend_rules(self):
        sm = BackendStateMachine()
        sm.receive(StartupMessage(params={"user": "test"}))
        sm.send(AuthenticationOk())
        assert sm.phase == _P.INITIALIZATION

    def test_receive_invalid_raises_with_receive_action(self):
        sm = BackendStateMachine()
        with pytest.raises(StateMachineError, match="Cannot receive"):
            sm.receive(Query(query_string="SELECT 1"))

    def test_send_invalid_raises_with_send_action(self):
        sm = BackendStateMachine(phase=_P.READY)
        with pytest.raises(StateMachineError, match="Cannot send"):
            sm.send(DataRow(columns=[b"1"]))


# ---------------------------------------------------------------------------
# Frontend transition rules — per-phase coverage
# ---------------------------------------------------------------------------


class TestFrontendStartupRules:
    def test_ssl_request(self):
        sm = FrontendStateMachine()
        sm.send(SSLRequest())
        assert sm.phase == _P.SSL_NEGOTIATION

    def test_gss_enc_request(self):
        sm = FrontendStateMachine()
        sm.send(GSSEncRequest())
        assert sm.phase == _P.GSS_NEGOTIATION

    def test_startup_message_stays(self):
        sm = FrontendStateMachine()
        sm.send(StartupMessage(params={"user": "test"}))
        assert sm.phase == _P.STARTUP

    def test_cancel_request_stays(self):
        sm = FrontendStateMachine()
        sm.send(CancelRequest(process_id=1, secret_key=b"\x00" * 4))
        assert sm.phase == _P.STARTUP

    def test_terminate(self):
        sm = FrontendStateMachine()
        sm.send(Terminate())
        assert sm.phase == _P.TERMINATED


class TestFrontendSSLNegotiationRules:
    def test_gss_enc_request(self):
        sm = FrontendStateMachine(phase=_P.SSL_NEGOTIATION)
        sm.send(GSSEncRequest())
        assert sm.phase == _P.GSS_NEGOTIATION

    def test_startup_message(self):
        sm = FrontendStateMachine(phase=_P.SSL_NEGOTIATION)
        sm.send(StartupMessage(params={"user": "test"}))
        assert sm.phase == _P.STARTUP

    def test_terminate(self):
        sm = FrontendStateMachine(phase=_P.SSL_NEGOTIATION)
        sm.send(Terminate())
        assert sm.phase == _P.TERMINATED


class TestFrontendGSSNegotiationRules:
    def test_startup_message(self):
        sm = FrontendStateMachine(phase=_P.GSS_NEGOTIATION)
        sm.send(StartupMessage(params={"user": "test"}))
        assert sm.phase == _P.STARTUP

    def test_terminate(self):
        sm = FrontendStateMachine(phase=_P.GSS_NEGOTIATION)
        sm.send(Terminate())
        assert sm.phase == _P.TERMINATED


class TestFrontendAuthenticatingRules:
    def test_password_stays(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING)
        sm.send(PasswordMessage(password="secret"))
        assert sm.phase == _P.AUTHENTICATING

    def test_terminate(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING)
        sm.send(Terminate())
        assert sm.phase == _P.TERMINATED


class TestFrontendSASLInitialRules:
    def test_sasl_initial_response_stays(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING_SASL_INITIAL)
        sm.send(SASLInitialResponse(mechanism="SCRAM-SHA-256", data=b"x"))
        assert sm.phase == _P.AUTHENTICATING_SASL_INITIAL

    def test_terminate(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING_SASL_INITIAL)
        sm.send(Terminate())
        assert sm.phase == _P.TERMINATED


class TestFrontendSASLContinueRules:
    def test_sasl_response_stays(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING_SASL_CONTINUE)
        sm.send(SASLResponse(data=b"x"))
        assert sm.phase == _P.AUTHENTICATING_SASL_CONTINUE

    def test_terminate(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING_SASL_CONTINUE)
        sm.send(Terminate())
        assert sm.phase == _P.TERMINATED


class TestFrontendReadyRules:
    def test_query(self):
        sm = FrontendStateMachine(phase=_P.READY)
        sm.send(Query(query_string="SELECT 1"))
        assert sm.phase == _P.SIMPLE_QUERY

    def test_parse_starts_extended(self):
        sm = FrontendStateMachine(phase=_P.READY)
        sm.send(Parse(statement="s", query="SELECT 1"))
        assert sm.phase == _P.EXTENDED_QUERY
        assert sm._state.in_extended_batch is True
        assert sm._state.pending_syncs == 1

    def test_bind_starts_extended(self):
        sm = FrontendStateMachine(phase=_P.READY)
        sm.send(Bind(portal="", statement="s"))
        assert sm.phase == _P.EXTENDED_QUERY

    def test_execute_starts_extended(self):
        sm = FrontendStateMachine(phase=_P.READY)
        sm.send(Execute(portal="", max_rows=0))
        assert sm.phase == _P.EXTENDED_QUERY

    def test_describe_starts_extended(self):
        sm = FrontendStateMachine(phase=_P.READY)
        sm.send(Describe(kind="S", name="s"))
        assert sm.phase == _P.EXTENDED_QUERY

    def test_close_starts_extended(self):
        sm = FrontendStateMachine(phase=_P.READY)
        sm.send(Close(kind="S", name="s"))
        assert sm.phase == _P.EXTENDED_QUERY

    def test_sync_from_ready(self):
        sm = FrontendStateMachine(phase=_P.READY)
        sm.send(Sync())
        assert sm.phase == _P.EXTENDED_QUERY
        assert sm._state.in_extended_batch is False
        assert sm._state.pending_syncs == 1

    def test_flush_stays(self):
        sm = FrontendStateMachine(phase=_P.READY)
        sm.send(Flush())
        assert sm.phase == _P.READY

    def test_function_call(self):
        sm = FrontendStateMachine(phase=_P.READY)
        sm.send(FunctionCall(function_oid=1))
        assert sm.phase == _P.FUNCTION_CALL

    def test_terminate(self):
        sm = FrontendStateMachine(phase=_P.READY)
        sm.send(Terminate())
        assert sm.phase == _P.TERMINATED


class TestFrontendSimpleQueryRules:
    def test_terminate_only_allowed_send(self):
        sm = FrontendStateMachine(phase=_P.SIMPLE_QUERY)
        sm.send(Terminate())
        assert sm.phase == _P.TERMINATED

    def test_no_pipelining(self):
        sm = FrontendStateMachine(phase=_P.SIMPLE_QUERY)
        with pytest.raises(StateMachineError):
            sm.send(Query(query_string="SELECT 2"))


class TestFrontendExtendedQueryRules:
    def test_parse_continues(self):
        sm = FrontendStateMachine(phase=_P.EXTENDED_QUERY)
        sm._state = replace(sm._state, in_extended_batch=True, pending_syncs=1)
        sm.send(Parse(statement="s", query="q"))
        assert sm._state.pending_syncs == 1

    def test_sync_ends_batch(self):
        sm = FrontendStateMachine(phase=_P.EXTENDED_QUERY)
        sm._state = replace(sm._state, in_extended_batch=True, pending_syncs=1)
        sm.send(Sync())
        assert sm._state.in_extended_batch is False
        assert sm._state.pending_syncs == 1

    def test_sync_without_batch_adds_sync_point(self):
        sm = FrontendStateMachine(phase=_P.EXTENDED_QUERY)
        sm._state = replace(sm._state, in_extended_batch=False, pending_syncs=1)
        sm.send(Sync())
        assert sm._state.pending_syncs == 2

    def test_flush_stays(self):
        sm = FrontendStateMachine(phase=_P.EXTENDED_QUERY)
        sm._state = replace(sm._state, in_extended_batch=True, pending_syncs=1)
        sm.send(Flush())
        assert sm.phase == _P.EXTENDED_QUERY

    def test_terminate(self):
        sm = FrontendStateMachine(phase=_P.EXTENDED_QUERY)
        sm._state = replace(sm._state, pending_syncs=1)
        sm.send(Terminate())
        assert sm.phase == _P.TERMINATED


class TestFrontendCopyInRules:
    def test_copy_data_stays(self):
        sm = FrontendStateMachine(phase=_P.COPY_IN)
        sm.send(CopyData(data=b"row"))
        assert sm.phase == _P.COPY_IN

    def test_copy_done(self):
        sm = FrontendStateMachine(phase=_P.COPY_IN)
        sm.send(CopyDone())
        assert sm.phase == _P.SIMPLE_QUERY

    def test_copy_fail(self):
        sm = FrontendStateMachine(phase=_P.COPY_IN)
        sm.send(CopyFail(error_message="abort"))
        assert sm.phase == _P.SIMPLE_QUERY

    def test_terminate(self):
        sm = FrontendStateMachine(phase=_P.COPY_IN)
        sm.send(Terminate())
        assert sm.phase == _P.TERMINATED

    def test_cannot_send_query(self):
        sm = FrontendStateMachine(phase=_P.COPY_IN)
        with pytest.raises(StateMachineError):
            sm.send(Query(query_string="SELECT 1"))


class TestFrontendCopyOutRules:
    def test_terminate_only(self):
        sm = FrontendStateMachine(phase=_P.COPY_OUT)
        sm.send(Terminate())
        assert sm.phase == _P.TERMINATED

    def test_cannot_send_copy_data(self):
        sm = FrontendStateMachine(phase=_P.COPY_OUT)
        with pytest.raises(StateMachineError):
            sm.send(CopyData(data=b"x"))


class TestFrontendFunctionCallRules:
    def test_terminate_only(self):
        sm = FrontendStateMachine(phase=_P.FUNCTION_CALL)
        sm.send(Terminate())
        assert sm.phase == _P.TERMINATED


# ---------------------------------------------------------------------------
# Backend receive rules (messages FROM the server)
# ---------------------------------------------------------------------------


class TestBackendMsgStartupRules:
    def test_negotiate_protocol_version_stays(self):
        sm = FrontendStateMachine()
        sm.send(StartupMessage(params={"user": "test"}))
        sm.receive(NegotiateProtocolVersion(newest_minor=0, unrecognized=[]))
        assert sm.phase == _P.STARTUP

    def test_auth_ok_to_initialization(self):
        sm = FrontendStateMachine()
        sm.send(StartupMessage(params={"user": "test"}))
        sm.receive(AuthenticationOk())
        assert sm.phase == _P.INITIALIZATION

    def test_auth_sasl_to_sasl_initial(self):
        sm = FrontendStateMachine()
        sm.send(StartupMessage(params={"user": "test"}))
        sm.receive(AuthenticationSASL(mechanisms=["SCRAM-SHA-256"]))
        assert sm.phase == _P.AUTHENTICATING_SASL_INITIAL

    def test_auth_cleartext_to_authenticating(self):
        sm = FrontendStateMachine()
        sm.send(StartupMessage(params={"user": "test"}))
        sm.receive(AuthenticationCleartextPassword())
        assert sm.phase == _P.AUTHENTICATING

    def test_auth_md5_to_authenticating(self):
        sm = FrontendStateMachine()
        sm.send(StartupMessage(params={"user": "test"}))
        sm.receive(AuthenticationMD5Password(salt=b"\x00" * 4))
        assert sm.phase == _P.AUTHENTICATING

    def test_error_to_failed(self):
        sm = FrontendStateMachine()
        sm.send(StartupMessage(params={"user": "test"}))
        sm.receive(ErrorResponse(fields={"S": "FATAL", "M": "err"}))
        assert sm.phase == _P.FAILED


class TestBackendMsgAuthenticatingRules:
    def test_auth_ok(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING)
        sm.receive(AuthenticationOk())
        assert sm.phase == _P.INITIALIZATION

    def test_auth_sasl_transition(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING)
        sm.receive(AuthenticationSASL(mechanisms=["SCRAM-SHA-256"]))
        assert sm.phase == _P.AUTHENTICATING_SASL_INITIAL

    def test_cleartext_stays(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING)
        sm.receive(AuthenticationCleartextPassword())
        assert sm.phase == _P.AUTHENTICATING

    def test_md5_stays(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING)
        sm.receive(AuthenticationMD5Password(salt=b"\x00" * 4))
        assert sm.phase == _P.AUTHENTICATING

    def test_gss_continue_stays(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING)
        sm.receive(AuthenticationGSSContinue(data=b"x"))
        assert sm.phase == _P.AUTHENTICATING

    def test_error_to_failed(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING)
        sm.receive(ErrorResponse(fields={"S": "FATAL", "M": "err"}))
        assert sm.phase == _P.FAILED


class TestBackendMsgSASLRules:
    def test_sasl_continue_from_initial(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING_SASL_INITIAL)
        sm.receive(AuthenticationSASLContinue(data=b"x"))
        assert sm.phase == _P.AUTHENTICATING_SASL_CONTINUE

    def test_auth_ok_from_initial(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING_SASL_INITIAL)
        sm.receive(AuthenticationOk())
        assert sm.phase == _P.INITIALIZATION

    def test_sasl_final_from_continue(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING_SASL_CONTINUE)
        sm.receive(AuthenticationSASLFinal(data=b"x"))
        assert sm.phase == _P.AUTHENTICATING

    def test_sasl_continue_stays_in_continue(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING_SASL_CONTINUE)
        sm.receive(AuthenticationSASLContinue(data=b"x"))
        assert sm.phase == _P.AUTHENTICATING_SASL_CONTINUE

    def test_auth_ok_from_continue(self):
        sm = FrontendStateMachine(phase=_P.AUTHENTICATING_SASL_CONTINUE)
        sm.receive(AuthenticationOk())
        assert sm.phase == _P.INITIALIZATION


class TestBackendMsgInitializationRules:
    def test_backend_key_data_stays(self):
        sm = FrontendStateMachine(phase=_P.INITIALIZATION)
        sm.receive(BackendKeyData(process_id=1, secret_key=b"\x00" * 4))
        assert sm.phase == _P.INITIALIZATION

    def test_ready_for_query(self):
        sm = FrontendStateMachine(phase=_P.INITIALIZATION)
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == _P.READY

    def test_notice_stays(self):
        sm = FrontendStateMachine(phase=_P.INITIALIZATION)
        sm.receive(NoticeResponse(fields={"S": "NOTICE", "M": "x"}))
        assert sm.phase == _P.INITIALIZATION

    def test_parameter_status_stays(self):
        sm = FrontendStateMachine(phase=_P.INITIALIZATION)
        sm.receive(ParameterStatus(name="x", value="y"))
        assert sm.phase == _P.INITIALIZATION

    def test_error_to_failed(self):
        sm = FrontendStateMachine(phase=_P.INITIALIZATION)
        sm.receive(ErrorResponse(fields={"S": "FATAL", "M": "err"}))
        assert sm.phase == _P.FAILED


class TestBackendMsgReadyRules:
    def test_notice_stays(self):
        sm = FrontendStateMachine(phase=_P.READY)
        sm.receive(NoticeResponse(fields={"S": "NOTICE", "M": "x"}))
        assert sm.phase == _P.READY

    def test_parameter_status_stays(self):
        sm = FrontendStateMachine(phase=_P.READY)
        sm.receive(ParameterStatus(name="x", value="y"))
        assert sm.phase == _P.READY

    def test_notification_stays(self):
        sm = FrontendStateMachine(phase=_P.READY)
        sm.receive(NotificationResponse(process_id=1, channel="c", payload="p"))
        assert sm.phase == _P.READY

    def test_error_stays(self):
        sm = FrontendStateMachine(phase=_P.READY)
        sm.receive(ErrorResponse(fields={"S": "ERROR", "M": "x"}))
        assert sm.phase == _P.READY


class TestBackendMsgSimpleQueryRules:
    def test_row_description_stays(self):
        sm = FrontendStateMachine(phase=_P.SIMPLE_QUERY)
        sm.receive(RowDescription(fields=[]))
        assert sm.phase == _P.SIMPLE_QUERY

    def test_data_row_stays(self):
        sm = FrontendStateMachine(phase=_P.SIMPLE_QUERY)
        sm.receive(DataRow(columns=[b"1"]))
        assert sm.phase == _P.SIMPLE_QUERY

    def test_command_complete_stays(self):
        sm = FrontendStateMachine(phase=_P.SIMPLE_QUERY)
        sm.receive(CommandComplete(tag="SELECT 1"))
        assert sm.phase == _P.SIMPLE_QUERY

    def test_empty_query_response_stays(self):
        sm = FrontendStateMachine(phase=_P.SIMPLE_QUERY)
        sm.receive(EmptyQueryResponse())
        assert sm.phase == _P.SIMPLE_QUERY

    def test_ready_for_query(self):
        sm = FrontendStateMachine(phase=_P.SIMPLE_QUERY)
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == _P.READY

    def test_copy_in_response(self):
        sm = FrontendStateMachine(phase=_P.SIMPLE_QUERY)
        sm.receive(CopyInResponse(overall_format=0, col_formats=[]))
        assert sm.phase == _P.COPY_IN

    def test_copy_out_response(self):
        sm = FrontendStateMachine(phase=_P.SIMPLE_QUERY)
        sm.receive(CopyOutResponse(overall_format=0, col_formats=[]))
        assert sm.phase == _P.COPY_OUT

    def test_error_stays(self):
        sm = FrontendStateMachine(phase=_P.SIMPLE_QUERY)
        sm.receive(ErrorResponse(fields={"S": "ERROR", "M": "x"}))
        assert sm.phase == _P.SIMPLE_QUERY


class TestBackendMsgExtendedQueryRules:
    def _make_sm(self, pending_syncs=1, in_batch=True):
        sm = FrontendStateMachine(phase=_P.EXTENDED_QUERY)
        sm._state = replace(sm._state, pending_syncs=pending_syncs, in_extended_batch=in_batch)
        return sm

    def test_parse_complete_stays(self):
        sm = self._make_sm()
        sm.receive(ParseComplete())
        assert sm.phase == _P.EXTENDED_QUERY

    def test_bind_complete_stays(self):
        sm = self._make_sm()
        sm.receive(BindComplete())
        assert sm.phase == _P.EXTENDED_QUERY

    def test_close_complete_stays(self):
        sm = self._make_sm()
        sm.receive(CloseComplete())
        assert sm.phase == _P.EXTENDED_QUERY

    def test_no_data_stays(self):
        sm = self._make_sm()
        sm.receive(NoData())
        assert sm.phase == _P.EXTENDED_QUERY

    def test_parameter_description_stays(self):
        sm = self._make_sm()
        sm.receive(ParameterDescription(type_oids=[23]))
        assert sm.phase == _P.EXTENDED_QUERY

    def test_row_description_stays(self):
        sm = self._make_sm()
        sm.receive(RowDescription(fields=[]))
        assert sm.phase == _P.EXTENDED_QUERY

    def test_data_row_stays(self):
        sm = self._make_sm()
        sm.receive(DataRow(columns=[b"1"]))
        assert sm.phase == _P.EXTENDED_QUERY

    def test_command_complete_stays(self):
        sm = self._make_sm()
        sm.receive(CommandComplete(tag="SELECT 1"))
        assert sm.phase == _P.EXTENDED_QUERY

    def test_portal_suspended_stays(self):
        sm = self._make_sm()
        sm.receive(PortalSuspended())
        assert sm.phase == _P.EXTENDED_QUERY

    def test_ready_for_query_resolves_sync(self):
        sm = self._make_sm(pending_syncs=2)
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == _P.EXTENDED_QUERY
        assert sm._state.pending_syncs == 1

    def test_ready_for_query_last_sync_returns_ready(self):
        sm = self._make_sm(pending_syncs=1)
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == _P.READY
        assert sm._state.pending_syncs == 0

    def test_copy_in_response(self):
        sm = self._make_sm()
        sm.receive(CopyInResponse(overall_format=0, col_formats=[]))
        assert sm.phase == _P.COPY_IN

    def test_copy_out_response(self):
        sm = self._make_sm()
        sm.receive(CopyOutResponse(overall_format=0, col_formats=[]))
        assert sm.phase == _P.COPY_OUT

    def test_error_stays(self):
        sm = self._make_sm()
        sm.receive(ErrorResponse(fields={"S": "ERROR", "M": "x"}))
        assert sm.phase == _P.EXTENDED_QUERY


class TestBackendMsgCopyInRules:
    def test_command_complete_stays(self):
        sm = FrontendStateMachine(phase=_P.COPY_IN)
        sm.receive(CommandComplete(tag="COPY 0"))
        assert sm.phase == _P.COPY_IN

    def test_ready_for_query(self):
        sm = FrontendStateMachine(phase=_P.COPY_IN)
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == _P.READY

    def test_error_stays(self):
        sm = FrontendStateMachine(phase=_P.COPY_IN)
        sm.receive(ErrorResponse(fields={"S": "ERROR", "M": "x"}))
        assert sm.phase == _P.COPY_IN


class TestBackendMsgCopyOutRules:
    def test_copy_data_stays(self):
        sm = FrontendStateMachine(phase=_P.COPY_OUT)
        sm.receive(CopyData(data=b"row"))
        assert sm.phase == _P.COPY_OUT

    def test_copy_done(self):
        sm = FrontendStateMachine(phase=_P.COPY_OUT)
        sm.receive(CopyDone())
        assert sm.phase == _P.SIMPLE_QUERY

    def test_command_complete_stays(self):
        sm = FrontendStateMachine(phase=_P.COPY_OUT)
        sm.receive(CommandComplete(tag="COPY 2"))
        assert sm.phase == _P.COPY_OUT

    def test_ready_for_query(self):
        sm = FrontendStateMachine(phase=_P.COPY_OUT)
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == _P.READY

    def test_error_stays(self):
        sm = FrontendStateMachine(phase=_P.COPY_OUT)
        sm.receive(ErrorResponse(fields={"S": "ERROR", "M": "x"}))
        assert sm.phase == _P.COPY_OUT


class TestBackendMsgFunctionCallRules:
    def test_function_call_response(self):
        sm = FrontendStateMachine(phase=_P.FUNCTION_CALL)
        sm.receive(FunctionCallResponse(result=b"x"))
        assert sm.phase == _P.SIMPLE_QUERY

    def test_command_complete_stays(self):
        sm = FrontendStateMachine(phase=_P.FUNCTION_CALL)
        sm.receive(CommandComplete(tag="x"))
        assert sm.phase == _P.FUNCTION_CALL

    def test_ready_for_query(self):
        sm = FrontendStateMachine(phase=_P.FUNCTION_CALL)
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm.phase == _P.READY

    def test_error_to_simple_query(self):
        sm = FrontendStateMachine(phase=_P.FUNCTION_CALL)
        sm.receive(ErrorResponse(fields={"S": "ERROR", "M": "x"}))
        assert sm.phase == _P.SIMPLE_QUERY


class TestBackendMsgSSLNegotiationRules:
    def test_ssl_response(self):
        sm = FrontendStateMachine(phase=_P.SSL_NEGOTIATION)
        sm.receive(SSLResponse(accepted=True))
        assert sm.phase == _P.STARTUP

    def test_error_to_failed(self):
        sm = FrontendStateMachine(phase=_P.SSL_NEGOTIATION)
        sm.receive(ErrorResponse(fields={"S": "FATAL", "M": "err"}))
        assert sm.phase == _P.FAILED


class TestBackendMsgGSSNegotiationRules:
    def test_gss_response(self):
        sm = FrontendStateMachine(phase=_P.GSS_NEGOTIATION)
        sm.receive(GSSResponse(accepted=True))
        assert sm.phase == _P.STARTUP

    def test_error_to_failed(self):
        sm = FrontendStateMachine(phase=_P.GSS_NEGOTIATION)
        sm.receive(ErrorResponse(fields={"S": "FATAL", "M": "err"}))
        assert sm.phase == _P.FAILED


# ---------------------------------------------------------------------------
# Terminal phases
# ---------------------------------------------------------------------------


class TestTerminalPhases:
    def test_terminated_rejects_frontend_send(self):
        sm = FrontendStateMachine(phase=_P.TERMINATED)
        with pytest.raises(StateMachineError):
            sm.send(Terminate())

    def test_terminated_rejects_backend_receive(self):
        sm = FrontendStateMachine(phase=_P.TERMINATED)
        with pytest.raises(StateMachineError):
            sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))

    def test_failed_rejects_frontend_send(self):
        sm = FrontendStateMachine(phase=_P.FAILED)
        with pytest.raises(StateMachineError):
            sm.send(Terminate())

    def test_failed_rejects_backend_receive(self):
        sm = FrontendStateMachine(phase=_P.FAILED)
        with pytest.raises(StateMachineError):
            sm.receive(AuthenticationOk())


# ---------------------------------------------------------------------------
# Pipelining edge cases (unit-level)
# ---------------------------------------------------------------------------


class TestPipeliningEdgeCases:
    def test_ext_continue_after_sync_starts_new_batch(self):
        """After Sync ends a batch, the next Parse starts a new batch."""
        sm = FrontendStateMachine(phase=_P.EXTENDED_QUERY)
        sm._state = replace(sm._state, in_extended_batch=False, pending_syncs=1)
        sm.send(Parse(statement="s", query="q"))
        assert sm._state.in_extended_batch is True
        assert sm._state.pending_syncs == 2

    def test_multiple_syncs_increment_pending(self):
        sm = FrontendStateMachine(phase=_P.EXTENDED_QUERY)
        sm._state = replace(sm._state, in_extended_batch=False, pending_syncs=1)
        sm.send(Sync())
        assert sm._state.pending_syncs == 2
        sm.send(Sync())
        assert sm._state.pending_syncs == 3

    def test_ready_for_query_clamps_to_zero(self):
        """If pending_syncs somehow goes negative, it clamps to 0."""
        sm = FrontendStateMachine(phase=_P.EXTENDED_QUERY)
        sm._state = replace(sm._state, pending_syncs=0)
        sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
        assert sm._state.pending_syncs == 0
        assert sm.phase == _P.READY
