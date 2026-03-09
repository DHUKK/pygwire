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
from pygwire.constants import ConnectionPhase
from pygwire.state_machine import FrontendStateMachine

sm = FrontendStateMachine(phase=ConnectionPhase.STARTUP)
```

**Parameters:**

- `phase` (`ConnectionPhase`, default `STARTUP`): Initial connection phase.

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
| `is_active` | `bool` | `True` if not in `TERMINATED` or `FAILED` |
| `pending_syncs` | `int` | Number of pending Sync responses (for pipelined extended queries) |

---

## `BackendStateMachine`

Tracks protocol state from the server's perspective. Same API as `FrontendStateMachine`.

```python
from pygwire.constants import ConnectionPhase
from pygwire.state_machine import BackendStateMachine

sm = BackendStateMachine(phase=ConnectionPhase.STARTUP)
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
| `AUTHENTICATING_SASL_INITIAL` | SASL authentication initial response |
| `AUTHENTICATING_SASL_CONTINUE` | SASL authentication continuation |
| `INITIALIZATION` | Post-auth setup (ParameterStatus, BackendKeyData) |
| `READY` | Idle, ready for queries |
| `SIMPLE_QUERY` | Simple query protocol active |
| `EXTENDED_QUERY` | Extended query protocol active |
| `COPY_IN` | COPY FROM stdin active |
| `COPY_OUT` | COPY TO stdout active |
| `COPY_BOTH` | Bidirectional copy (streaming replication) |
| `FUNCTION_CALL` | Legacy function call active |
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
                                          TERMINATED
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
--8<-- "examples/docs/state_machine_basic.py"
```

## Error handling

```python
--8<-- "examples/docs/state_machine_error.py"
```

## Proxy usage

A proxy needs state machines for both sides:

```python
--8<-- "examples/docs/state_machine_proxy.py"
```

Both state machines should stay in the same phase. A mismatch indicates a protocol violation.

!!! tip "Connection classes"
    If you do not need to manage the decoder and state machine separately, use `FrontendConnection` or `BackendConnection` from `pygwire.connection`. They coordinate both automatically. See the [Connection reference](connection.md).
