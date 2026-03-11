# State Machine

The state machine tracks connection phases at the level of detail pygwire needs for correct decoding and useful lifecycle information. It is not intended to enforce every rule of the PostgreSQL protocol.

Phases exist for three reasons:

1. **Framing.** The PostgreSQL wire protocol uses different message framing depending on the connection phase. During `STARTUP` messages have no identifier byte (just length + payload). During `SSL_NEGOTIATION` and `GSS_NEGOTIATION` the server responds with a single byte. All other phases use standard framing (identifier byte + length + payload). The state machine is used to determine the framing mode the codec should use.

2. **Message disambiguation.** Some message identifiers are reused across phases. The `'p'` byte can mean `PasswordMessage`, `SASLInitialResponse`, or `SASLResponse` depending on the current authentication phase. The SASL sub-phases (`AUTHENTICATING_SASL_INITIAL`, `AUTHENTICATING_SASL_CONTINUE`) exist so the codec can decode the correct message type.

3. **Lifecycle tracking.** Phases like `READY`, `SIMPLE_QUERY`, `EXTENDED_QUERY`, and the `COPY_*` phases let consumers answer questions like "is it safe to send a query?" or "is the server still processing my request?". These phases are not required by the codec itself but are useful for building clients, proxies, and connection pools (etc.) on top of pygwire.

The state machine does **not** validate message ordering within a phase. For example, it will not reject a `DataRow` sent before `RowDescription` during `SIMPLE_QUERY`, because both are valid message types in that phase. Enforcing that kind of sequencing would require SQL-level knowledge and belongs in a higher-level layer built on top of pygwire.

## State machines

| State Machine | Role | Use case |
|---------------|------|----------|
| `FrontendStateMachine` | Client | Track client-side protocol phase |
| `BackendStateMachine` | Server | Track server-side protocol phase |

Both track a `ConnectionPhase` and raise `StateMachineError` if a message type is not valid for the current phase.

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
