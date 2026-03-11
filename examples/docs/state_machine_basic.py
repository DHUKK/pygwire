"""State Machine: Basic usage."""

from pygwire import FrontendStateMachine, TransactionStatus
from pygwire.messages import (
    AuthenticationOk,
    BackendKeyData,
    ParameterStatus,
    ReadyForQuery,
    StartupMessage,
)

sm = FrontendStateMachine()
print(sm.phase)  # ConnectionPhase.STARTUP

# Record messages as you send/receive them
sm.send(StartupMessage(params={"user": "postgres", "database": "mydb"}))
print(sm.phase)  # ConnectionPhase.AUTHENTICATING

sm.receive(AuthenticationOk())
sm.receive(ParameterStatus(name="server_version", value="15.0"))
sm.receive(BackendKeyData(process_id=1234, secret_key=b"\x00\x00\x00\x01"))
sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
print(sm.phase)  # ConnectionPhase.READY
