"""Sans-I/O state machine for PostgreSQL wire protocol connection lifecycle.

This module provides state machines that track the connection phase for both
frontend (client) and backend (server) roles. The state machine tracks the
phase transitions that pygwire needs (for framing, message disambiguation,
and lifecycle) and does not go finer-grained than that. It does not validate
message ordering within a phase.

Usage (Frontend)::

    sm = FrontendStateMachine()
    # After sending messages.StartupMessage
    sm.send(messages.StartupMessage(...))
    # When receiving messages.Authentication
    sm.receive(messages.AuthenticationMD5Password(...))
    # After sending messages.PasswordMessage
    sm.send(messages.PasswordMessage(...))
    # When receiving messages.ReadyForQuery
    sm.receive(messages.ReadyForQuery(...))
    # Now in READY state

Usage (Backend)::

    sm = BackendStateMachine()
    # After receiving messages.StartupMessage
    sm.receive(messages.StartupMessage(...))
    # After sending messages.Authentication
    sm.send(messages.AuthenticationMD5Password(...))
    # When receiving messages.PasswordMessage
    sm.receive(messages.PasswordMessage(...))
    # After sending messages.ReadyForQuery
    sm.send(messages.ReadyForQuery(...))
    # Now in READY state
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum

from pygwire import messages
from pygwire.constants import ConnectionPhase
from pygwire.exceptions import StateMachineError

__all__ = [
    "BackendStateMachine",
    "FrontendStateMachine",
    "MessageAction",
]

_P = ConnectionPhase


class MessageAction(StrEnum):
    """Action being performed on a message (send or receive)."""

    SEND = "send"
    RECEIVE = "receive"


class _Transition:
    """Transition to a fixed phase."""

    __slots__ = ("_phase",)

    def __init__(self, phase: ConnectionPhase) -> None:
        self._phase = phase

    def __call__(self, sm: _StateMachineCore) -> None:
        sm._state = replace(sm._state, phase=self._phase)


class _Stay:
    """Remain in the current phase (no-op)."""

    __slots__ = ()

    def __call__(self, sm: _StateMachineCore) -> None:
        pass


class _ExtStart:
    """Enter extended query from READY and start a new batch."""

    __slots__ = ()

    def __call__(self, sm: _StateMachineCore) -> None:
        sm._state = replace(
            sm._state,
            phase=_P.EXTENDED_QUERY,
            in_extended_batch=True,
            pending_syncs=sm._state.pending_syncs + 1,
        )


class _ExtContinue:
    """Continue in extended query with pipelining support."""

    __slots__ = ()

    def __call__(self, sm: _StateMachineCore) -> None:
        if not sm._state.in_extended_batch:
            sm._state = replace(
                sm._state,
                in_extended_batch=True,
                pending_syncs=sm._state.pending_syncs + 1,
            )


class _ExtSync:
    """Sync message in extended query ends batch or adds sync point."""

    __slots__ = ()

    def __call__(self, sm: _StateMachineCore) -> None:
        if sm._state.in_extended_batch:
            sm._state = replace(sm._state, in_extended_batch=False)
        else:
            sm._state = replace(sm._state, pending_syncs=sm._state.pending_syncs + 1)


class _ExtReadyForQuery:
    """ReadyForQuery in extended query resolves one pending sync."""

    __slots__ = ()

    def __call__(self, sm: _StateMachineCore) -> None:
        new_pending = sm._state.pending_syncs - 1
        if new_pending <= 0:
            sm._state = replace(sm._state, phase=_P.READY, in_extended_batch=False, pending_syncs=0)
        else:
            sm._state = replace(sm._state, pending_syncs=new_pending)


class _CopyDone:
    """CopyDone/CopyFail ends COPY phase and returns to SIMPLE_QUERY."""

    __slots__ = ()

    def __call__(self, sm: _StateMachineCore) -> None:
        sm._state = replace(sm._state, phase=_P.SIMPLE_QUERY)


class _SyncFromReady:
    """Standalone Sync from READY enters EXTENDED_QUERY with a sync point."""

    __slots__ = ()

    def __call__(self, sm: _StateMachineCore) -> None:
        sm._state = replace(
            sm._state,
            phase=_P.EXTENDED_QUERY,
            pending_syncs=sm._state.pending_syncs + 1,
            in_extended_batch=False,
        )


stay = _Stay()
ext_start = _ExtStart()
ext_continue = _ExtContinue()
ext_sync = _ExtSync()
ext_rfq = _ExtReadyForQuery()
copy_done = _CopyDone()
sync_from_ready = _SyncFromReady()


def to(phase: ConnectionPhase) -> _Transition:
    return _Transition(phase)


_Rule = tuple[
    tuple[type[messages.PGMessage], ...],
    Callable[["_StateMachineCore"], None],
]

_FRONTEND_MSG_RULES: dict[ConnectionPhase, list[_Rule]] = {
    _P.STARTUP: [
        ((messages.SSLRequest,), to(_P.SSL_NEGOTIATION)),
        ((messages.GSSEncRequest,), to(_P.GSS_NEGOTIATION)),
        ((messages.StartupMessage, messages.CancelRequest), stay),
        ((messages.Terminate,), to(_P.TERMINATED)),
    ],
    _P.SSL_NEGOTIATION: [
        ((messages.GSSEncRequest,), to(_P.GSS_NEGOTIATION)),
        ((messages.StartupMessage,), to(_P.STARTUP)),
        ((messages.Terminate,), to(_P.TERMINATED)),
    ],
    _P.GSS_NEGOTIATION: [
        ((messages.StartupMessage,), to(_P.STARTUP)),
        ((messages.Terminate,), to(_P.TERMINATED)),
    ],
    _P.AUTHENTICATING: [
        ((messages.PasswordMessage,), stay),
        ((messages.Terminate,), to(_P.TERMINATED)),
    ],
    _P.AUTHENTICATING_SASL_INITIAL: [
        ((messages.SASLInitialResponse,), stay),
        ((messages.Terminate,), to(_P.TERMINATED)),
    ],
    _P.AUTHENTICATING_SASL_CONTINUE: [
        ((messages.SASLResponse,), stay),
        ((messages.Terminate,), to(_P.TERMINATED)),
    ],
    _P.INITIALIZATION: [
        ((messages.Terminate,), to(_P.TERMINATED)),
    ],
    _P.READY: [
        ((messages.Query,), to(_P.SIMPLE_QUERY)),
        (
            (messages.Parse, messages.Bind, messages.Execute, messages.Describe, messages.Close),
            ext_start,
        ),
        ((messages.Sync,), sync_from_ready),
        ((messages.Flush,), stay),
        ((messages.FunctionCall,), to(_P.FUNCTION_CALL)),
        ((messages.Terminate,), to(_P.TERMINATED)),
    ],
    _P.SIMPLE_QUERY: [
        ((messages.Terminate,), to(_P.TERMINATED)),
    ],
    _P.EXTENDED_QUERY: [
        (
            (messages.Parse, messages.Bind, messages.Execute, messages.Describe, messages.Close),
            ext_continue,
        ),
        ((messages.Flush,), stay),
        ((messages.Sync,), ext_sync),
        ((messages.Terminate,), to(_P.TERMINATED)),
    ],
    _P.COPY_IN: [
        ((messages.CopyData,), stay),
        ((messages.CopyDone, messages.CopyFail), copy_done),
        ((messages.Terminate,), to(_P.TERMINATED)),
    ],
    _P.COPY_OUT: [
        ((messages.Terminate,), to(_P.TERMINATED)),
    ],
    _P.FUNCTION_CALL: [
        ((messages.Terminate,), to(_P.TERMINATED)),
    ],
}

_BACKEND_MSG_RULES: dict[ConnectionPhase, list[_Rule]] = {
    _P.STARTUP: [
        ((messages.NegotiateProtocolVersion,), stay),
        ((messages.AuthenticationOk,), to(_P.INITIALIZATION)),
        ((messages.AuthenticationSASL,), to(_P.AUTHENTICATING_SASL_INITIAL)),
        (
            (
                messages.AuthenticationCleartextPassword,
                messages.AuthenticationMD5Password,
                messages.AuthenticationKerberosV5,
                messages.AuthenticationGSS,
                messages.AuthenticationSSPI,
            ),
            to(_P.AUTHENTICATING),
        ),
        ((messages.ErrorResponse,), to(_P.FAILED)),
    ],
    _P.SSL_NEGOTIATION: [
        ((messages.SSLResponse,), to(_P.STARTUP)),
        ((messages.ErrorResponse,), to(_P.FAILED)),
    ],
    _P.GSS_NEGOTIATION: [
        ((messages.GSSResponse,), to(_P.STARTUP)),
        ((messages.ErrorResponse,), to(_P.FAILED)),
    ],
    _P.AUTHENTICATING: [
        ((messages.AuthenticationOk,), to(_P.INITIALIZATION)),
        ((messages.AuthenticationSASL,), to(_P.AUTHENTICATING_SASL_INITIAL)),
        (
            (
                messages.AuthenticationCleartextPassword,
                messages.AuthenticationMD5Password,
                messages.AuthenticationKerberosV5,
                messages.AuthenticationGSS,
                messages.AuthenticationGSSContinue,
                messages.AuthenticationSSPI,
            ),
            stay,
        ),
        ((messages.ErrorResponse,), to(_P.FAILED)),
    ],
    _P.AUTHENTICATING_SASL_INITIAL: [
        ((messages.AuthenticationSASLContinue,), to(_P.AUTHENTICATING_SASL_CONTINUE)),
        ((messages.AuthenticationOk,), to(_P.INITIALIZATION)),
        ((messages.ErrorResponse,), to(_P.FAILED)),
    ],
    _P.AUTHENTICATING_SASL_CONTINUE: [
        ((messages.AuthenticationSASLFinal,), to(_P.AUTHENTICATING)),
        ((messages.AuthenticationSASLContinue,), stay),
        ((messages.AuthenticationOk,), to(_P.INITIALIZATION)),
        ((messages.ErrorResponse,), to(_P.FAILED)),
    ],
    _P.INITIALIZATION: [
        ((messages.BackendKeyData,), stay),
        ((messages.ReadyForQuery,), to(_P.READY)),
        ((messages.NoticeResponse, messages.ParameterStatus, messages.NotificationResponse), stay),
        ((messages.ErrorResponse,), to(_P.FAILED)),
    ],
    _P.READY: [
        # "Any phase" messages allowed (Notice, ParameterStatus, Notification)
        ((messages.NoticeResponse, messages.ParameterStatus, messages.NotificationResponse), stay),
        ((messages.ErrorResponse,), stay),
    ],
    _P.SIMPLE_QUERY: [
        (
            (
                messages.RowDescription,
                messages.DataRow,
                messages.CommandComplete,
                messages.EmptyQueryResponse,
            ),
            stay,
        ),
        ((messages.ReadyForQuery,), to(_P.READY)),
        ((messages.CopyInResponse,), to(_P.COPY_IN)),
        ((messages.CopyOutResponse,), to(_P.COPY_OUT)),
        ((messages.NoticeResponse, messages.ParameterStatus, messages.NotificationResponse), stay),
        ((messages.ErrorResponse,), stay),
    ],
    _P.EXTENDED_QUERY: [
        (
            (
                messages.ParseComplete,
                messages.BindComplete,
                messages.CloseComplete,
                messages.ParameterDescription,
                messages.NoData,
                messages.RowDescription,
                messages.DataRow,
                messages.CommandComplete,
                messages.EmptyQueryResponse,
                messages.PortalSuspended,
            ),
            stay,
        ),
        ((messages.ReadyForQuery,), ext_rfq),
        ((messages.CopyInResponse,), to(_P.COPY_IN)),
        ((messages.CopyOutResponse,), to(_P.COPY_OUT)),
        ((messages.NoticeResponse, messages.ParameterStatus, messages.NotificationResponse), stay),
        ((messages.ErrorResponse,), stay),
    ],
    _P.COPY_IN: [
        ((messages.CommandComplete,), stay),
        ((messages.ReadyForQuery,), to(_P.READY)),
        ((messages.NoticeResponse, messages.ParameterStatus, messages.NotificationResponse), stay),
        ((messages.ErrorResponse,), stay),
    ],
    _P.COPY_OUT: [
        ((messages.CopyData,), stay),
        ((messages.CopyDone,), copy_done),
        ((messages.CommandComplete,), stay),
        ((messages.ReadyForQuery,), to(_P.READY)),
        ((messages.NoticeResponse, messages.ParameterStatus, messages.NotificationResponse), stay),
        ((messages.ErrorResponse,), stay),
    ],
    _P.FUNCTION_CALL: [
        ((messages.FunctionCallResponse,), to(_P.SIMPLE_QUERY)),
        ((messages.CommandComplete,), stay),
        ((messages.ReadyForQuery,), to(_P.READY)),
        ((messages.NoticeResponse, messages.ParameterStatus, messages.NotificationResponse), stay),
        ((messages.ErrorResponse,), to(_P.SIMPLE_QUERY)),
    ],
}

_TERMINAL_PHASES = frozenset(
    {
        _P.TERMINATED,
        _P.FAILED,
    }
)


def _generate_hints(rules: dict[ConnectionPhase, list[_Rule]]) -> dict[ConnectionPhase, str]:
    """Generate error hints from transition rules listing valid message types per phase."""
    hints = {}
    for phase, phase_rules in rules.items():
        msg_names = [msg_type.__name__ for msg_types, _ in phase_rules for msg_type in msg_types]
        if not msg_names:
            continue
        if len(msg_names) == 1:
            hints[phase] = f"expected {msg_names[0]}"
        else:
            hints[phase] = f"expected {', '.join(msg_names[:-1])}, or {msg_names[-1]}"
    return hints


_FRONTEND_PHASE_HINTS = _generate_hints(_FRONTEND_MSG_RULES)
_BACKEND_PHASE_HINTS = _generate_hints(_BACKEND_MSG_RULES)


@dataclass(frozen=True, slots=True)
class _State:
    """Immutable state for the state machine.

    All state transitions create a new _State instance rather than mutating in place.
    """

    phase: ConnectionPhase
    in_extended_batch: bool = False
    pending_syncs: int = 0


class _StateMachineCore:
    """Table-driven state machine core shared by Frontend and Backend.

    The two public classes (FrontendStateMachine, BackendStateMachine) differ
    only in which transition table is used for send() vs receive().

    All state transitions are declaratively defined in the rule tables.
    Uses immutable state objects for all state transitions.
    """

    __slots__ = ("_state",)

    def __init__(
        self,
        phase: ConnectionPhase = ConnectionPhase.STARTUP,
    ) -> None:
        self._state = _State(phase=phase)

    @property
    def phase(self) -> ConnectionPhase:
        """Current connection phase."""
        return self._state.phase

    @property
    def is_ready(self) -> bool:
        """True if the connection is ready to accept queries."""
        return self._state.phase == ConnectionPhase.READY

    @property
    def is_active(self) -> bool:
        """True if the connection is active (not terminated or failed)."""
        return self._state.phase not in _TERMINAL_PHASES

    @property
    def pending_syncs(self) -> int:
        """Number of pending messages.Sync responses (for pipelined extended queries)."""
        return self._state.pending_syncs

    def _process_frontend_msg(self, msg: object, action: MessageAction) -> None:
        """Process a frontend message."""
        self._process(msg, rules=_FRONTEND_MSG_RULES, hints=_FRONTEND_PHASE_HINTS, action=action)

    def _process_backend_msg(self, msg: object, action: MessageAction) -> None:
        """Process a backend message."""
        self._process(msg, rules=_BACKEND_MSG_RULES, hints=_BACKEND_PHASE_HINTS, action=action)

    def _process(
        self,
        msg: object,
        rules: dict[ConnectionPhase, list[_Rule]],
        hints: dict[ConnectionPhase, str],
        action: MessageAction,
    ) -> None:
        """Process a message against the given transition table."""
        msg_type = type(msg).__name__
        phase = self._state.phase

        phase_rules = rules.get(phase)
        if phase_rules is None:
            raise StateMachineError(f"Cannot {action} {msg_type} in phase {phase.name}")

        for msg_types, action_fn in phase_rules:
            if isinstance(msg, msg_types):
                action_fn(self)
                return

        hint = hints.get(phase, "")
        base = f"Cannot {action} {msg_type} in phase {phase.name}"
        if hint:
            raise StateMachineError(f"{base}; {hint}")
        raise StateMachineError(base)


class FrontendStateMachine(_StateMachineCore):
    """State machine for frontend (client) connection lifecycle.

    Tracks the current phase and validates that messages sent and received
    are appropriate for the current state.

    Three backend messages are accepted in any phase (except STARTUP/TERMINATED):
    - messages.NoticeResponse
    - messages.ParameterStatus
    - messages.NotificationResponse

    messages.ErrorResponse transitions to FAILED in most phases.

    Pipelining Support:
    ----------------------
    Extended query protocol supports pipelining via the messages.Sync message.
    Simple query protocol does NOT support pipelining (per PostgreSQL spec 54.2.4).

    The state machine tracks pending_syncs to handle pipelined extended query batches.
    """

    def send(self, msg: messages.FrontendMessage | messages.SpecialMessage) -> None:
        """Process a message being sent by the frontend.

        Args:
            msg: The message to send

        Raises:
            messages.StateMachineError: If the message is not valid for the current phase
        """
        self._process_frontend_msg(msg, action=MessageAction.SEND)

    def receive(self, msg: messages.BackendMessage) -> None:
        """Process a message received from the backend.

        Args:
            msg: The message received

        Raises:
            messages.StateMachineError: If the message is not valid for the current phase
        """
        self._process_backend_msg(msg, action=MessageAction.RECEIVE)


class BackendStateMachine(_StateMachineCore):
    """State machine for backend (server) connection lifecycle.

    Tracks the current phase and validates that messages sent and received
    are appropriate for the current state. This is the mirror of
    FrontendStateMachine.

    Pipelining Support:
    ----------------------
    Extended query protocol supports pipelining via the messages.Sync message.
    Simple query protocol does NOT support pipelining (per PostgreSQL spec 54.2.4).
    """

    def receive(self, msg: messages.FrontendMessage | messages.SpecialMessage) -> None:
        """Process a message received from the frontend.

        Args:
            msg: The message received

        Raises:
            messages.StateMachineError: If the message is not valid for the current phase
        """
        self._process_frontend_msg(msg, action=MessageAction.RECEIVE)

    def send(self, msg: messages.BackendMessage) -> None:
        """Process a message being sent by the backend.

        Args:
            msg: The message to send

        Raises:
            messages.StateMachineError: If the message is not valid for the current phase
        """
        self._process_backend_msg(msg, action=MessageAction.SEND)
