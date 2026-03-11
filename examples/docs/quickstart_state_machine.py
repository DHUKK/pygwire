"""Quickstart: Tracking connection state."""

from pygwire import FrontendStateMachine, TransactionStatus
from pygwire.messages import (
    AuthenticationOk,
    BackendKeyData,
    ParameterStatus,
    Query,
    ReadyForQuery,
    StartupMessage,
)

sm = FrontendStateMachine()

# Track what you send
sm.send(StartupMessage(params={"user": "postgres", "database": "mydb"}))
print(sm.phase)  # ConnectionPhase.AUTHENTICATING

# Track what you receive
sm.receive(AuthenticationOk())
sm.receive(ParameterStatus(name="server_version", value="15.0"))
sm.receive(BackendKeyData(process_id=1234, secret_key=b"\x00\x00\x00\x01"))
sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
print(sm.phase)  # ConnectionPhase.READY

# Raises StateMachineError for messages invalid in the current phase
sm.send(Query(query_string="SELECT 1"))
print(sm.phase)  # ConnectionPhase.SIMPLE_QUERY
