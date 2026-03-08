# State Machine

The state machine tracks the PostgreSQL connection lifecycle and validates that messages are sent and received in the correct order for the current protocol phase.

## State machines

| State Machine | Role | Use case |
|---------------|------|----------|
| `FrontendStateMachine` | Client | Validate client-side protocol flow |
| `BackendStateMachine` | Server | Validate server-side protocol flow |

Both track a `ConnectionPhase` and raise `StateMachineError` if an invalid message is sent or received.

---

## `FrontendStateMachine`

Tracks protocol state from the client's perspective.

```python
from pygwire import FrontendStateMachine, ConnectionPhase

sm = FrontendStateMachine(phase=ConnectionPhase.STARTUP, allow_pipelining=True)
```

**Parameters:**

- `phase` (`ConnectionPhase`, default `STARTUP`): Initial connection phase.
- `allow_pipelining` (`bool`, default `True`): Whether to allow extended query pipelining.

### Methods

#### `send(msg) -> None`

Record sending a frontend message. Raises `StateMachineError` if the message is not valid for the current phase.

#### `receive(msg) -> None`

Record receiving a backend message. Raises `StateMachineError` if the message is not valid for the current phase.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `phase` | `ConnectionPhase` | Current connection phase |
| `is_ready` | `bool` | `True` if phase is `READY` |
| `is_active` | `bool` | `True` if not in `TERMINATING`, `TERMINATED`, or `FAILED` |
| `pending_syncs` | `int` | Number of pending Sync responses (for pipelined extended queries) |

---

## `BackendStateMachine`

Tracks protocol state from the server's perspective. Same API as `FrontendStateMachine`.

```python
from pygwire import BackendStateMachine

sm = BackendStateMachine(phase=ConnectionPhase.STARTUP, allow_pipelining=True)
```

**Parameters:** Same as `FrontendStateMachine`.

### Methods

#### `receive(msg) -> None`

Record receiving a frontend message. Raises `StateMachineError` if invalid for the current phase.

#### `send(msg) -> None`

Record sending a backend message. Raises `StateMachineError` if invalid for the current phase.

### Properties

Same as `FrontendStateMachine`.

---

## `ConnectionPhase`

`Enum` of connection lifecycle phases.

| Phase | Description |
|-------|-------------|
| `STARTUP` | Initial state, waiting for startup message |
| `SSL_NEGOTIATION` | SSL/TLS negotiation in progress |
| `GSS_NEGOTIATION` | GSS encryption negotiation in progress |
| `AUTHENTICATING` | Authentication exchange active |
| `INITIALIZATION` | Post-auth setup (ParameterStatus, BackendKeyData) |
| `READY` | Idle, ready for queries |
| `SIMPLE_QUERY` | Simple query protocol active |
| `EXTENDED_QUERY` | Extended query protocol active |
| `COPY_IN` | COPY FROM stdin active |
| `COPY_OUT` | COPY TO stdout active |
| `COPY_BOTH` | Bidirectional copy (streaming replication) |
| `FUNCTION_CALL` | Legacy function call active |
| `TERMINATING` | Terminate message sent |
| `TERMINATED` | Connection closed |
| `FAILED` | Unrecoverable error |

### Typical phase flow

```
STARTUP → AUTHENTICATING → INITIALIZATION → READY
                                              ↕
                                         SIMPLE_QUERY
                                         EXTENDED_QUERY
                                         COPY_IN / COPY_OUT
                                              ↓
                                         TERMINATING → TERMINATED
```

---

## `StateMachineError`

```python
from pygwire.state_machine import StateMachineError
```

Raised when an invalid message is sent or received for the current connection phase. Subclass of `ProtocolError`.

---

## Basic usage

```python
from pygwire import FrontendStateMachine, ConnectionPhase
from pygwire.constants import TransactionStatus
from pygwire.messages import (
    AuthenticationOk,
    BackendKeyData,
    ParameterStatus,
    Query,
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
```

## Error handling

```python
from pygwire import FrontendStateMachine
from pygwire.messages import Query
from pygwire.state_machine import StateMachineError

sm = FrontendStateMachine()

try:
    # Can't send a query before completing startup
    sm.send(Query(query_string="SELECT 1"))
except StateMachineError as e:
    print(f"Invalid: {e}")
```

## Proxy usage

A proxy needs state machines for both sides:

```python
from pygwire import FrontendStateMachine, BackendStateMachine

frontend_sm = FrontendStateMachine()
backend_sm = BackendStateMachine()

# When a client message arrives:
frontend_sm.send(client_msg)    # Client sent it
backend_sm.receive(client_msg)  # Server received it

# When a server message arrives:
backend_sm.send(server_msg)     # Server sent it
frontend_sm.receive(server_msg) # Client received it
```

Both state machines should stay in the same phase. A mismatch indicates a protocol violation.

!!! tip "Connection classes"
    If you do not need to manage the decoder and state machine separately, use `FrontendConnection` or `BackendConnection` from `pygwire.connection`. They coordinate both automatically. See the [Connection reference](connection.md).
