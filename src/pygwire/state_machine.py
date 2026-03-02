"""Sans-I/O state machine for PostgreSQL wire protocol connection lifecycle.

This module provides state machines that track the connection phase for both
frontend (client) and backend (server) roles. The state machine validates
whether a given message type is legal to send or receive in the current phase.

Usage (Frontend)::

    sm = FrontendStateMachine()
    # After sending StartupMessage
    sm.send(StartupMessage(...))
    # When receiving Authentication
    sm.receive(AuthenticationMD5Password(...))
    # After sending PasswordMessage
    sm.send(PasswordMessage(...))
    # When receiving ReadyForQuery
    sm.receive(ReadyForQuery(...))
    # Now in READY state

Usage (Backend)::

    sm = BackendStateMachine()
    # After receiving StartupMessage
    sm.receive(StartupMessage(...))
    # After sending Authentication
    sm.send(AuthenticationMD5Password(...))
    # When receiving PasswordMessage
    sm.receive(PasswordMessage(...))
    # After sending ReadyForQuery
    sm.send(ReadyForQuery(...))
    # Now in READY state
"""

from __future__ import annotations

from enum import Enum, auto

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
    BackendKeyData,
    BackendMessage,
    Bind,
    BindComplete,
    CancelRequest,
    Close,
    CloseComplete,
    CommandComplete,
    CopyBothResponse,
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
    FrontendMessage,
    FunctionCall,
    FunctionCallResponse,
    GSSEncRequest,
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
    ProtocolError,
    Query,
    ReadyForQuery,
    RowDescription,
    SASLInitialResponse,
    SASLResponse,
    SpecialMessage,
    SSLRequest,
    StartupMessage,
    Sync,
    Terminate,
)


class StateMachineError(ProtocolError):
    """Raised when an invalid message is sent/received for the current state."""


class ConnectionPhase(Enum):
    """Connection phases in the PostgreSQL wire protocol lifecycle.

    The protocol follows this general flow:

    Frontend (Client):
        STARTUP → AUTHENTICATING → READY → QUERYING/EXTENDED/COPY → READY → ...

    Backend (Server):
        STARTUP → AUTHENTICATING → READY → QUERYING/EXTENDED/COPY → READY → ...

    Either side can enter TERMINATED at any time by sending/receiving Terminate.
    Either side can enter FAILED at any time by receiving ErrorResponse.
    """

    # Initial state - waiting for or sending startup message
    STARTUP = auto()

    # SSL/GSS negotiation (optional)
    SSL_NEGOTIATION = auto()
    GSS_NEGOTIATION = auto()

    # Authentication loop
    AUTHENTICATING = auto()

    # Post-auth, waiting for BackendKeyData and ParameterStatus messages
    INITIALIZATION = auto()

    # Ready to accept queries
    READY = auto()

    # Simple query protocol active
    SIMPLE_QUERY = auto()

    # Extended query protocol active
    EXTENDED_QUERY = auto()

    # COPY mode (COPY IN, COPY OUT, or COPY BOTH)
    COPY_IN = auto()
    COPY_OUT = auto()
    COPY_BOTH = auto()

    # Function call active (legacy)
    FUNCTION_CALL = auto()

    # Connection terminating gracefully
    TERMINATING = auto()

    # Connection terminated
    TERMINATED = auto()

    # Connection failed (received ErrorResponse during startup/auth)
    FAILED = auto()


class FrontendStateMachine:
    """State machine for frontend (client) connection lifecycle.

    Tracks the current phase and validates that messages sent and received
    are appropriate for the current state.

    Three backend messages are accepted in any phase (except STARTUP/TERMINATED):
    - NoticeResponse
    - ParameterStatus
    - NotificationResponse

    ErrorResponse transitions to FAILED in most phases.

    Pipelining Support:
    ----------------------
    Extended query protocol supports pipelining via the Sync message.
    Simple query protocol does NOT support pipelining (per PostgreSQL spec 54.2.4).

    The state machine tracks pending_syncs to handle pipelined extended query batches.
    """

    __slots__ = ("_phase", "_in_extended_batch", "_pending_syncs", "_allow_pipelining")

    def __init__(
        self,
        phase: ConnectionPhase = ConnectionPhase.STARTUP,
        allow_pipelining: bool = True,
    ) -> None:
        self._phase = phase
        # Track whether we're in an extended query batch (before Sync)
        self._in_extended_batch = False
        # Track pending Sync responses for pipelining support (extended query)
        self._pending_syncs = 0
        # Whether to allow pipelining (can be disabled for strict validation)
        self._allow_pipelining = allow_pipelining

    @property
    def phase(self) -> ConnectionPhase:
        """Current connection phase."""
        return self._phase

    @property
    def is_ready(self) -> bool:
        """True if the connection is ready to accept queries."""
        return self._phase == ConnectionPhase.READY

    @property
    def is_active(self) -> bool:
        """True if the connection is active (not terminated or failed)."""
        return self._phase not in (
            ConnectionPhase.TERMINATING,
            ConnectionPhase.TERMINATED,
            ConnectionPhase.FAILED,
        )

    @property
    def pending_syncs(self) -> int:
        """Number of pending Sync responses (for pipelined extended queries)."""
        return self._pending_syncs

    def send(self, msg: FrontendMessage | SpecialMessage) -> None:
        """Process a message being sent by the frontend.

        Args:
            msg: The message to send

        Raises:
            StateMachineError: If the message is not valid for the current phase
        """
        msg_type = type(msg).__name__
        phase = self._phase

        # Terminate can be sent from any active phase
        if isinstance(msg, Terminate):
            if phase in (
                ConnectionPhase.TERMINATING,
                ConnectionPhase.TERMINATED,
                ConnectionPhase.FAILED,
            ):
                raise StateMachineError(f"Cannot send {msg_type} in phase {phase.name}")
            self._phase = ConnectionPhase.TERMINATING
            return

        # Phase-specific validation
        if phase == ConnectionPhase.STARTUP:
            if isinstance(msg, (StartupMessage, SSLRequest, GSSEncRequest, CancelRequest)):
                if isinstance(msg, SSLRequest):
                    self._phase = ConnectionPhase.SSL_NEGOTIATION
                elif isinstance(msg, GSSEncRequest):
                    self._phase = ConnectionPhase.GSS_NEGOTIATION
                # StartupMessage keeps us in STARTUP until we receive a response
                # CancelRequest closes the connection immediately (no response)
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "expected StartupMessage, SSLRequest, GSSEncRequest, or CancelRequest"
            )

        elif phase == ConnectionPhase.SSL_NEGOTIATION:
            # After SSL response, send StartupMessage, GSSEncRequest, or CancelRequest
            # CancelRequest can be sent on its own ephemeral connection after SSL negotiation
            if isinstance(msg, (StartupMessage, GSSEncRequest, CancelRequest)):
                if isinstance(msg, GSSEncRequest):
                    self._phase = ConnectionPhase.GSS_NEGOTIATION
                elif isinstance(msg, StartupMessage):
                    self._phase = ConnectionPhase.STARTUP
                # CancelRequest stays in SSL_NEGOTIATION and closes connection
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "expected StartupMessage, GSSEncRequest, or CancelRequest"
            )

        elif phase == ConnectionPhase.GSS_NEGOTIATION:
            # After GSS response, send StartupMessage
            if isinstance(msg, StartupMessage):
                self._phase = ConnectionPhase.STARTUP
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; expected StartupMessage"
            )

        elif phase == ConnectionPhase.AUTHENTICATING:
            if isinstance(msg, (PasswordMessage, SASLInitialResponse, SASLResponse)):
                # Stay in AUTHENTICATING until we receive AuthenticationOk
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; expected authentication response"
            )

        elif phase == ConnectionPhase.INITIALIZATION:
            # During initialization, frontend doesn't send anything except Terminate
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "waiting for backend initialization to complete"
            )

        elif phase == ConnectionPhase.READY:
            if isinstance(msg, Query):
                self._phase = ConnectionPhase.SIMPLE_QUERY
                # Note: simple query does not support pipelining
                return
            elif isinstance(msg, (Parse, Bind, Execute, Describe, Close)):
                self._phase = ConnectionPhase.EXTENDED_QUERY
                self._in_extended_batch = True
                self._pending_syncs += 1  # Start a new extended query batch
                return
            elif isinstance(msg, Sync):
                # Sync in READY - server will respond with ReadyForQuery
                # Transition to EXTENDED_QUERY to handle the response
                self._phase = ConnectionPhase.EXTENDED_QUERY
                self._pending_syncs += 1
                self._in_extended_batch = False  # Not in a batch, just a sync point
                return
            elif isinstance(msg, Flush):
                # Flush in READY is a true no-op (doesn't expect response)
                return
            elif isinstance(msg, FunctionCall):
                self._phase = ConnectionPhase.FUNCTION_CALL
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "expected Query, Parse, Bind, Execute, Describe, Close, Sync, Flush, or FunctionCall"
            )

        elif phase == ConnectionPhase.SIMPLE_QUERY:
            # Simple query protocol does NOT support pipelining per PostgreSQL spec
            # "Use of the extended query protocol allows pipelining" - PG docs 54.2.4
            # Must wait for ReadyForQuery before sending another Query
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "simple query protocol does not support pipelining "
                "(use extended query protocol for pipelining)"
            )

        elif phase == ConnectionPhase.EXTENDED_QUERY:
            if isinstance(msg, (Parse, Bind, Execute, Describe, Close, Flush)):
                # Pipelining: if we're not in a batch, start a new one
                if not self._in_extended_batch and isinstance(
                    msg, (Parse, Bind, Execute, Describe, Close)
                ):
                    if self._allow_pipelining:
                        self._in_extended_batch = True
                        self._pending_syncs += 1
                        return
                    raise StateMachineError(
                        f"Cannot send {msg_type} in phase {phase.name}; "
                        "must wait for ReadyForQuery (pipelining disabled)"
                    )
                # Continue in current extended query batch
                return
            elif isinstance(msg, Sync):
                if self._in_extended_batch:
                    # Sync ends the current extended query batch
                    self._in_extended_batch = False
                else:
                    # Additional Sync sent after previous Sync (pipelined sync points)
                    # Each Sync gets its own ReadyForQuery response
                    self._pending_syncs += 1
                # Stay in EXTENDED_QUERY until we receive ReadyForQuery
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "expected Parse, Bind, Execute, Describe, Close, Sync, or Flush"
            )

        elif phase == ConnectionPhase.COPY_IN:
            if isinstance(msg, (CopyData, CopyDone, CopyFail)):
                # CopyDone/CopyFail transition back to waiting for CommandComplete
                if isinstance(msg, (CopyDone, CopyFail)):
                    self._phase = ConnectionPhase.SIMPLE_QUERY
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "expected CopyData, CopyDone, or CopyFail"
            )

        elif phase == ConnectionPhase.COPY_OUT:
            # In COPY OUT, frontend only receives data
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "waiting for COPY OUT data from backend"
            )

        elif phase == ConnectionPhase.COPY_BOTH:
            if isinstance(msg, (CopyData, CopyDone, CopyFail)):
                # CopyDone/CopyFail transition back to waiting for backend
                if isinstance(msg, (CopyDone, CopyFail)):
                    self._phase = ConnectionPhase.SIMPLE_QUERY
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "expected CopyData, CopyDone, or CopyFail"
            )

        elif phase == ConnectionPhase.FUNCTION_CALL:
            # In function call, we wait for backend response
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; waiting for function call response"
            )

        elif phase == ConnectionPhase.TERMINATING:
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; connection is terminating"
            )

        else:
            raise StateMachineError(f"Cannot send {msg_type} in phase {phase.name}")

    def receive(self, msg: BackendMessage) -> None:
        """Process a message received from the backend.

        Args:
            msg: The message received

        Raises:
            StateMachineError: If the message is not valid for the current phase
        """
        msg_type = type(msg).__name__
        phase = self._phase

        # Three messages are accepted in any phase (except STARTUP/TERMINATED/FAILED)
        if isinstance(msg, (NoticeResponse, ParameterStatus, NotificationResponse)):
            if phase in (
                ConnectionPhase.STARTUP,
                ConnectionPhase.SSL_NEGOTIATION,
                ConnectionPhase.GSS_NEGOTIATION,
                ConnectionPhase.TERMINATED,
            ):
                raise StateMachineError(f"Cannot receive {msg_type} in phase {phase.name}")
            # These don't change state
            return

        # ErrorResponse handling
        if isinstance(msg, ErrorResponse):
            if phase in (
                ConnectionPhase.STARTUP,
                ConnectionPhase.SSL_NEGOTIATION,
                ConnectionPhase.GSS_NEGOTIATION,
                ConnectionPhase.AUTHENTICATING,
                ConnectionPhase.INITIALIZATION,
            ):
                # Fatal during startup/auth
                self._phase = ConnectionPhase.FAILED
                return
            elif phase == ConnectionPhase.SIMPLE_QUERY:
                # Error in simple query - wait for ReadyForQuery
                return
            elif phase == ConnectionPhase.EXTENDED_QUERY:
                # Error in extended query - stay in extended query until ReadyForQuery
                return
            elif phase in (
                ConnectionPhase.COPY_IN,
                ConnectionPhase.COPY_OUT,
                ConnectionPhase.COPY_BOTH,
            ):
                # Error in COPY - stay in COPY phase until CopyDone/CopyFail
                # Client must send CopyFail to acknowledge the error
                return
            elif phase == ConnectionPhase.FUNCTION_CALL:
                # Error in function call - wait for ReadyForQuery
                self._phase = ConnectionPhase.SIMPLE_QUERY
                return
            # Other phases - don't change state
            return

        # Phase-specific validation
        if phase == ConnectionPhase.STARTUP:
            if isinstance(msg, NegotiateProtocolVersion):
                # Protocol version negotiation - stay in STARTUP
                return
            if isinstance(msg, AuthenticationOk):
                # Trust authentication - skip AUTHENTICATING phase
                self._phase = ConnectionPhase.INITIALIZATION
                return
            if isinstance(
                msg,
                (
                    Authentication,
                    AuthenticationCleartextPassword,
                    AuthenticationMD5Password,
                    AuthenticationKerberosV5,
                    AuthenticationGSS,
                    AuthenticationGSSContinue,
                    AuthenticationSSPI,
                    AuthenticationSASL,
                    AuthenticationSASLContinue,
                    AuthenticationSASLFinal,
                ),
            ):
                self._phase = ConnectionPhase.AUTHENTICATING
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "expected Authentication or NegotiateProtocolVersion"
            )

        elif phase == ConnectionPhase.SSL_NEGOTIATION:
            # SSL response is a single byte, not a message - handled externally
            # If we receive a message here, it's an error
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "expected single-byte SSL response"
            )

        elif phase == ConnectionPhase.GSS_NEGOTIATION:
            # GSS response is a single byte, not a message - handled externally
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "expected single-byte GSS response"
            )

        elif phase == ConnectionPhase.AUTHENTICATING:
            if isinstance(msg, AuthenticationOk):
                # Authentication successful - transition to INITIALIZATION
                self._phase = ConnectionPhase.INITIALIZATION
                return
            elif isinstance(
                msg,
                (
                    AuthenticationCleartextPassword,
                    AuthenticationMD5Password,
                    AuthenticationKerberosV5,
                    AuthenticationGSS,
                    AuthenticationGSSContinue,
                    AuthenticationSSPI,
                    AuthenticationSASL,
                    AuthenticationSASLContinue,
                    AuthenticationSASLFinal,
                ),
            ):
                # Continue authentication loop
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; expected Authentication message"
            )

        elif phase == ConnectionPhase.INITIALIZATION:
            if isinstance(msg, BackendKeyData):
                # BackendKeyData is sent during initialization
                return
            elif isinstance(msg, ReadyForQuery):
                # Initialization complete - ready for queries
                self._phase = ConnectionPhase.READY
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "expected BackendKeyData or ReadyForQuery"
            )

        elif phase == ConnectionPhase.READY:
            # In READY, we shouldn't receive messages except the "any phase" ones
            # (which are already handled above)
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "not expecting backend messages while idle"
            )

        elif phase == ConnectionPhase.SIMPLE_QUERY:
            if isinstance(msg, (RowDescription, DataRow, CommandComplete, EmptyQueryResponse)):
                # Query results
                return
            elif isinstance(msg, ReadyForQuery):
                # Simple query complete - back to READY
                # (no pipelining support, so no pending counter)
                self._phase = ConnectionPhase.READY
                return
            elif isinstance(msg, CopyInResponse):
                self._phase = ConnectionPhase.COPY_IN
                return
            elif isinstance(msg, CopyOutResponse):
                self._phase = ConnectionPhase.COPY_OUT
                return
            elif isinstance(msg, CopyBothResponse):
                self._phase = ConnectionPhase.COPY_BOTH
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "expected query results, ReadyForQuery, or Copy*Response"
            )

        elif phase == ConnectionPhase.EXTENDED_QUERY:
            if isinstance(
                msg,
                (
                    ParseComplete,
                    BindComplete,
                    CloseComplete,
                    ParameterDescription,
                    NoData,
                    RowDescription,
                    DataRow,
                    CommandComplete,
                    EmptyQueryResponse,
                    PortalSuspended,
                ),
            ):
                # Extended query results
                return
            elif isinstance(msg, ReadyForQuery):
                # Extended query batch complete - decrement pending syncs
                self._pending_syncs -= 1
                if self._pending_syncs > 0:
                    # Still have pending batches - stay in EXTENDED_QUERY
                    return
                # All batches complete - back to READY
                self._phase = ConnectionPhase.READY
                self._in_extended_batch = False
                return
            elif isinstance(msg, CopyInResponse):
                self._phase = ConnectionPhase.COPY_IN
                return
            elif isinstance(msg, CopyOutResponse):
                self._phase = ConnectionPhase.COPY_OUT
                return
            elif isinstance(msg, CopyBothResponse):
                self._phase = ConnectionPhase.COPY_BOTH
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "expected extended query results, ReadyForQuery, or Copy*Response"
            )

        elif phase == ConnectionPhase.COPY_IN:
            # In COPY IN, backend sends no data - just waits for frontend
            if isinstance(msg, (CommandComplete, ReadyForQuery)):
                if isinstance(msg, ReadyForQuery):
                    self._phase = ConnectionPhase.READY
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "expected CommandComplete or ReadyForQuery"
            )

        elif phase == ConnectionPhase.COPY_OUT:
            if isinstance(msg, (CopyData, CopyDone)):
                if isinstance(msg, CopyDone):
                    # COPY OUT complete - wait for CommandComplete
                    self._phase = ConnectionPhase.SIMPLE_QUERY
                return
            elif isinstance(msg, (CommandComplete, ReadyForQuery)):
                if isinstance(msg, ReadyForQuery):
                    self._phase = ConnectionPhase.READY
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "expected CopyData, CopyDone, CommandComplete, or ReadyForQuery"
            )

        elif phase == ConnectionPhase.COPY_BOTH:
            if isinstance(msg, (CopyData, CopyDone)):
                if isinstance(msg, CopyDone):
                    # COPY BOTH complete - wait for CommandComplete
                    self._phase = ConnectionPhase.SIMPLE_QUERY
                return
            elif isinstance(msg, (CommandComplete, ReadyForQuery)):
                if isinstance(msg, ReadyForQuery):
                    self._phase = ConnectionPhase.READY
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "expected CopyData, CopyDone, CommandComplete, or ReadyForQuery"
            )

        elif phase == ConnectionPhase.FUNCTION_CALL:
            if isinstance(msg, FunctionCallResponse):
                # Function call response - stay in phase until ReadyForQuery
                self._phase = ConnectionPhase.SIMPLE_QUERY
                return
            elif isinstance(msg, (CommandComplete, ReadyForQuery)):
                if isinstance(msg, ReadyForQuery):
                    self._phase = ConnectionPhase.READY
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "expected FunctionCallResponse, CommandComplete, or ReadyForQuery"
            )

        elif phase == ConnectionPhase.TERMINATING:
            # After Terminate, we shouldn't receive anything
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; connection is terminating"
            )

        else:
            raise StateMachineError(f"Cannot receive {msg_type} in phase {phase.name}")


class BackendStateMachine:
    """State machine for backend (server) connection lifecycle.

    Tracks the current phase and validates that messages sent and received
    are appropriate for the current state. This is the mirror of
    FrontendStateMachine.

    Pipelining Support:
    ----------------------
    Extended query protocol supports pipelining via the Sync message.
    Simple query protocol does NOT support pipelining (per PostgreSQL spec 54.2.4).
    """

    __slots__ = ("_phase", "_in_extended_batch", "_pending_syncs", "_allow_pipelining")

    def __init__(
        self,
        phase: ConnectionPhase = ConnectionPhase.STARTUP,
        allow_pipelining: bool = True,
    ) -> None:
        self._phase = phase
        self._in_extended_batch = False
        # Track pending Sync responses for pipelining support (extended query)
        self._pending_syncs = 0
        # Whether to allow pipelining (can be disabled for strict validation)
        self._allow_pipelining = allow_pipelining

    @property
    def phase(self) -> ConnectionPhase:
        """Current connection phase."""
        return self._phase

    @property
    def is_ready(self) -> bool:
        """True if the connection is ready to accept queries."""
        return self._phase == ConnectionPhase.READY

    @property
    def is_active(self) -> bool:
        """True if the connection is active (not terminated or failed)."""
        return self._phase not in (
            ConnectionPhase.TERMINATING,
            ConnectionPhase.TERMINATED,
            ConnectionPhase.FAILED,
        )

    @property
    def pending_syncs(self) -> int:
        """Number of pending Sync responses (for pipelined extended queries)."""
        return self._pending_syncs

    def receive(self, msg: FrontendMessage | SpecialMessage) -> None:
        """Process a message received from the frontend.

        Args:
            msg: The message received

        Raises:
            StateMachineError: If the message is not valid for the current phase
        """
        msg_type = type(msg).__name__
        phase = self._phase

        # Terminate can be received in any active phase
        if isinstance(msg, Terminate):
            if phase in (
                ConnectionPhase.TERMINATING,
                ConnectionPhase.TERMINATED,
                ConnectionPhase.FAILED,
            ):
                raise StateMachineError(f"Cannot receive {msg_type} in phase {phase.name}")
            self._phase = ConnectionPhase.TERMINATED
            return

        # Phase-specific validation
        if phase == ConnectionPhase.STARTUP:
            if isinstance(msg, (StartupMessage, SSLRequest, GSSEncRequest, CancelRequest)):
                if isinstance(msg, SSLRequest):
                    self._phase = ConnectionPhase.SSL_NEGOTIATION
                elif isinstance(msg, GSSEncRequest):
                    self._phase = ConnectionPhase.GSS_NEGOTIATION
                # StartupMessage stays in STARTUP until backend responds
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "expected StartupMessage, SSLRequest, GSSEncRequest, or CancelRequest"
            )

        elif phase == ConnectionPhase.SSL_NEGOTIATION:
            # After sending SSL response, receive StartupMessage or GSSEncRequest
            if isinstance(msg, (StartupMessage, GSSEncRequest)):
                if isinstance(msg, GSSEncRequest):
                    self._phase = ConnectionPhase.GSS_NEGOTIATION
                else:
                    self._phase = ConnectionPhase.STARTUP
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "expected StartupMessage or GSSEncRequest"
            )

        elif phase == ConnectionPhase.GSS_NEGOTIATION:
            # After sending GSS response, receive StartupMessage
            if isinstance(msg, StartupMessage):
                self._phase = ConnectionPhase.STARTUP
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; expected StartupMessage"
            )

        elif phase == ConnectionPhase.AUTHENTICATING:
            if isinstance(msg, (PasswordMessage, SASLInitialResponse, SASLResponse)):
                # Stay in AUTHENTICATING until we send AuthenticationOk
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; expected authentication response"
            )

        elif phase == ConnectionPhase.INITIALIZATION:
            # During initialization, backend sends messages (no receives)
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "backend is sending initialization messages"
            )

        elif phase == ConnectionPhase.READY:
            if isinstance(msg, Query):
                self._phase = ConnectionPhase.SIMPLE_QUERY
                return
            elif isinstance(msg, (Parse, Bind, Execute, Describe, Close)):
                self._phase = ConnectionPhase.EXTENDED_QUERY
                self._in_extended_batch = True
                self._pending_syncs += 1  # Start a new extended query batch
                return
            elif isinstance(msg, Sync):
                # Sync in READY - backend will respond with ReadyForQuery
                # Transition to EXTENDED_QUERY to handle sending the response
                self._phase = ConnectionPhase.EXTENDED_QUERY
                self._pending_syncs += 1
                self._in_extended_batch = False  # Not in a batch, just a sync point
                return
            elif isinstance(msg, Flush):
                # Flush in READY doesn't change state (no response expected)
                return
            elif isinstance(msg, FunctionCall):
                self._phase = ConnectionPhase.FUNCTION_CALL
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "expected Query, Parse, Bind, Execute, Describe, Close, Sync, Flush, or FunctionCall"
            )

        elif phase == ConnectionPhase.SIMPLE_QUERY:
            # Simple query protocol does NOT support pipelining per PostgreSQL spec
            # Backend is sending results, client cannot send more queries yet
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "backend is sending query results "
                "(simple query protocol does not support pipelining)"
            )

        elif phase == ConnectionPhase.EXTENDED_QUERY:
            if isinstance(msg, (Parse, Bind, Execute, Describe, Close, Flush)):
                # Pipelining: if we're not in a batch, start a new one
                if not self._in_extended_batch and isinstance(
                    msg, (Parse, Bind, Execute, Describe, Close)
                ):
                    if self._allow_pipelining:
                        self._in_extended_batch = True
                        self._pending_syncs += 1
                        return
                    raise StateMachineError(
                        f"Cannot receive {msg_type} in phase {phase.name}; "
                        "must wait for ReadyForQuery (pipelining disabled)"
                    )
                # Continue in current extended query batch
                return
            elif isinstance(msg, Sync):
                if self._in_extended_batch:
                    # Sync ends the current extended query batch
                    self._in_extended_batch = False
                else:
                    # Additional Sync received after previous Sync (pipelined sync points)
                    # Backend must send a ReadyForQuery for each Sync
                    self._pending_syncs += 1
                # Stay in EXTENDED_QUERY until backend sends ReadyForQuery
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "expected Parse, Bind, Execute, Describe, Close, Sync, or Flush"
            )

        elif phase == ConnectionPhase.COPY_IN:
            if isinstance(msg, (CopyData, CopyDone, CopyFail)):
                # CopyDone/CopyFail transition to sending CommandComplete
                if isinstance(msg, (CopyDone, CopyFail)):
                    self._phase = ConnectionPhase.SIMPLE_QUERY
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "expected CopyData, CopyDone, or CopyFail"
            )

        elif phase == ConnectionPhase.COPY_OUT:
            # In COPY OUT, backend is sending data (no receives)
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; backend is sending COPY OUT data"
            )

        elif phase == ConnectionPhase.COPY_BOTH:
            if isinstance(msg, (CopyData, CopyDone, CopyFail)):
                # CopyDone/CopyFail transition to sending CommandComplete
                if isinstance(msg, (CopyDone, CopyFail)):
                    self._phase = ConnectionPhase.SIMPLE_QUERY
                return
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "expected CopyData, CopyDone, or CopyFail"
            )

        elif phase == ConnectionPhase.FUNCTION_CALL:
            # In function call, backend is responding
            raise StateMachineError(
                f"Cannot receive {msg_type} in phase {phase.name}; "
                "backend is sending function call response"
            )

        else:
            raise StateMachineError(f"Cannot receive {msg_type} in phase {phase.name}")

    def send(self, msg: BackendMessage) -> None:
        """Process a message being sent by the backend.

        Args:
            msg: The message to send

        Raises:
            StateMachineError: If the message is not valid for the current phase
        """
        msg_type = type(msg).__name__
        phase = self._phase

        # Three messages can be sent in any phase (except TERMINATED/FAILED)
        if isinstance(msg, (NoticeResponse, ParameterStatus, NotificationResponse)):
            if phase in (ConnectionPhase.TERMINATED, ConnectionPhase.FAILED):
                raise StateMachineError(f"Cannot send {msg_type} in phase {phase.name}")
            # These don't change state
            return

        # ErrorResponse handling
        if isinstance(msg, ErrorResponse):
            if phase in (
                ConnectionPhase.STARTUP,
                ConnectionPhase.SSL_NEGOTIATION,
                ConnectionPhase.GSS_NEGOTIATION,
                ConnectionPhase.AUTHENTICATING,
                ConnectionPhase.INITIALIZATION,
            ):
                # Fatal during startup/auth
                self._phase = ConnectionPhase.FAILED
                return
            elif phase == ConnectionPhase.SIMPLE_QUERY:
                # Error in simple query - send ReadyForQuery next
                return
            elif phase == ConnectionPhase.EXTENDED_QUERY:
                # Error in extended query - stay in extended query until ReadyForQuery
                return
            elif phase in (
                ConnectionPhase.COPY_IN,
                ConnectionPhase.COPY_OUT,
                ConnectionPhase.COPY_BOTH,
            ):
                # Error in COPY - stay in COPY phase until CopyDone/CopyFail received
                # Then send ReadyForQuery to return to READY
                return
            elif phase == ConnectionPhase.FUNCTION_CALL:
                # Error in function call - send ReadyForQuery next
                self._phase = ConnectionPhase.SIMPLE_QUERY
                return
            # Other phases - don't change state
            return

        # Phase-specific validation
        if phase == ConnectionPhase.STARTUP:
            if isinstance(msg, NegotiateProtocolVersion):
                # Protocol version negotiation
                return
            if isinstance(msg, AuthenticationOk):
                # Trust authentication - skip AUTHENTICATING phase
                self._phase = ConnectionPhase.INITIALIZATION
                return
            if isinstance(
                msg,
                (
                    Authentication,
                    AuthenticationCleartextPassword,
                    AuthenticationMD5Password,
                    AuthenticationKerberosV5,
                    AuthenticationGSS,
                    AuthenticationGSSContinue,
                    AuthenticationSSPI,
                    AuthenticationSASL,
                    AuthenticationSASLContinue,
                    AuthenticationSASLFinal,
                ),
            ):
                self._phase = ConnectionPhase.AUTHENTICATING
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "expected Authentication or NegotiateProtocolVersion"
            )

        elif phase == ConnectionPhase.SSL_NEGOTIATION:
            # SSL response is a single byte, not a message - handled externally
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; expected single-byte SSL response"
            )

        elif phase == ConnectionPhase.GSS_NEGOTIATION:
            # GSS response is a single byte, not a message - handled externally
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; expected single-byte GSS response"
            )

        elif phase == ConnectionPhase.AUTHENTICATING:
            if isinstance(msg, AuthenticationOk):
                # Authentication successful - transition to INITIALIZATION
                self._phase = ConnectionPhase.INITIALIZATION
                return
            elif isinstance(
                msg,
                (
                    AuthenticationCleartextPassword,
                    AuthenticationMD5Password,
                    AuthenticationKerberosV5,
                    AuthenticationGSS,
                    AuthenticationGSSContinue,
                    AuthenticationSSPI,
                    AuthenticationSASL,
                    AuthenticationSASLContinue,
                    AuthenticationSASLFinal,
                ),
            ):
                # Continue authentication loop
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; expected Authentication message"
            )

        elif phase == ConnectionPhase.INITIALIZATION:
            if isinstance(msg, BackendKeyData):
                # BackendKeyData during initialization
                return
            elif isinstance(msg, ReadyForQuery):
                # Initialization complete
                self._phase = ConnectionPhase.READY
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "expected BackendKeyData or ReadyForQuery"
            )

        elif phase == ConnectionPhase.READY:
            # In READY, backend doesn't send messages except the "any phase" ones
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "not expecting to send backend messages while idle"
            )

        elif phase == ConnectionPhase.SIMPLE_QUERY:
            if isinstance(msg, (RowDescription, DataRow, CommandComplete, EmptyQueryResponse)):
                # Query results
                return
            elif isinstance(msg, ReadyForQuery):
                # Simple query complete - back to READY
                # (no pipelining support, so no pending counter)
                self._phase = ConnectionPhase.READY
                return
            elif isinstance(msg, CopyInResponse):
                self._phase = ConnectionPhase.COPY_IN
                return
            elif isinstance(msg, CopyOutResponse):
                self._phase = ConnectionPhase.COPY_OUT
                return
            elif isinstance(msg, CopyBothResponse):
                self._phase = ConnectionPhase.COPY_BOTH
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "expected query results, ReadyForQuery, or Copy*Response"
            )

        elif phase == ConnectionPhase.EXTENDED_QUERY:
            if isinstance(
                msg,
                (
                    ParseComplete,
                    BindComplete,
                    CloseComplete,
                    ParameterDescription,
                    NoData,
                    RowDescription,
                    DataRow,
                    CommandComplete,
                    EmptyQueryResponse,
                    PortalSuspended,
                ),
            ):
                # Extended query results
                return
            elif isinstance(msg, ReadyForQuery):
                # Extended query batch complete - decrement pending syncs
                self._pending_syncs -= 1
                if self._pending_syncs > 0:
                    # Still have pending batches - stay in EXTENDED_QUERY
                    return
                # All batches complete - back to READY
                self._phase = ConnectionPhase.READY
                self._in_extended_batch = False
                return
            elif isinstance(msg, CopyInResponse):
                self._phase = ConnectionPhase.COPY_IN
                return
            elif isinstance(msg, CopyOutResponse):
                self._phase = ConnectionPhase.COPY_OUT
                return
            elif isinstance(msg, CopyBothResponse):
                self._phase = ConnectionPhase.COPY_BOTH
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "expected extended query results, ReadyForQuery, or Copy*Response"
            )

        elif phase == ConnectionPhase.COPY_IN:
            # In COPY IN, backend waits for data (no sends except completion)
            if isinstance(msg, (CommandComplete, ReadyForQuery)):
                if isinstance(msg, ReadyForQuery):
                    self._phase = ConnectionPhase.READY
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "expected CommandComplete or ReadyForQuery"
            )

        elif phase == ConnectionPhase.COPY_OUT:
            if isinstance(msg, (CopyData, CopyDone)):
                if isinstance(msg, CopyDone):
                    # COPY OUT complete - send CommandComplete next
                    self._phase = ConnectionPhase.SIMPLE_QUERY
                return
            elif isinstance(msg, (CommandComplete, ReadyForQuery)):
                if isinstance(msg, ReadyForQuery):
                    self._phase = ConnectionPhase.READY
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "expected CopyData, CopyDone, CommandComplete, or ReadyForQuery"
            )

        elif phase == ConnectionPhase.COPY_BOTH:
            if isinstance(msg, (CopyData, CopyDone)):
                if isinstance(msg, CopyDone):
                    # COPY BOTH complete - send CommandComplete next
                    self._phase = ConnectionPhase.SIMPLE_QUERY
                return
            elif isinstance(msg, (CommandComplete, ReadyForQuery)):
                if isinstance(msg, ReadyForQuery):
                    self._phase = ConnectionPhase.READY
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "expected CopyData, CopyDone, CommandComplete, or ReadyForQuery"
            )

        elif phase == ConnectionPhase.FUNCTION_CALL:
            if isinstance(msg, FunctionCallResponse):
                # Function call response - send ReadyForQuery next
                self._phase = ConnectionPhase.SIMPLE_QUERY
                return
            elif isinstance(msg, (CommandComplete, ReadyForQuery)):
                if isinstance(msg, ReadyForQuery):
                    self._phase = ConnectionPhase.READY
                return
            raise StateMachineError(
                f"Cannot send {msg_type} in phase {phase.name}; "
                "expected FunctionCallResponse, CommandComplete, or ReadyForQuery"
            )

        else:
            raise StateMachineError(f"Cannot send {msg_type} in phase {phase.name}")
