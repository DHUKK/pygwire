"""Quickstart: Using Connection (decoder + state machine together)."""

from pygwire.connection import FrontendConnection
from pygwire.constants import TransactionStatus
from pygwire.messages import (
    AuthenticationOk,
    BackendKeyData,
    ParameterStatus,
    ReadyForQuery,
    StartupMessage,
)

conn = FrontendConnection()

# send() validates via state machine and returns wire bytes
wire_bytes = conn.send(StartupMessage(params={"user": "postgres", "database": "mydb"}))
print(conn.phase)  # ConnectionPhase.AUTHENTICATING

# receive() feeds bytes to decoder, validates each message, and yields them
server_data = (
    AuthenticationOk().to_wire()
    + ParameterStatus(name="server_version", value="15.0").to_wire()
    + BackendKeyData(process_id=1234, secret_key=b"\x00\x00\x00\x01").to_wire()
    + ReadyForQuery(status=TransactionStatus.IDLE).to_wire()
)
for msg in conn.receive(server_data):
    print(f"Received: {type(msg).__name__}")

print(conn.phase)  # ConnectionPhase.READY
