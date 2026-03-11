# Connection

The `Connection` classes coordinate a decoder and state machine together, providing a higher-level sans-I/O API for the PostgreSQL wire protocol.

## Overview

Without Connection, you manage a decoder and state machine separately:

```python
--8<-- "examples/docs/connection_overview_without.py"
```

With Connection, both are coordinated in a single object:

```python
--8<-- "examples/docs/connection_overview_with.py"
```

## Connection types

| Class | Role | Decoder | State Machine |
|-------|------|---------|---------------|
| `FrontendConnection` | Client | `BackendMessageDecoder` | `FrontendStateMachine` |
| `BackendConnection` | Server | `FrontendMessageDecoder` | `BackendStateMachine` |

---

## `Connection` (abstract base)

Base class. Use `FrontendConnection` or `BackendConnection`.

### Attributes

| Attribute | Type |
|-----------|------|
| `decoder` | `BackendMessageDecoder \| FrontendMessageDecoder` |
| `state_machine` | `FrontendStateMachine \| BackendStateMachine` |

### `send(msg) -> bytes`

Validate the message against the state machine, encode it to wire format, and call `on_send()`.

Returns the wire-format bytes.

Raises `StateMachineError` if the message is not valid for the current phase.

### `receive(data) -> Iterator[PGMessage]`

Feed raw bytes to the decoder and yield decoded messages. Each message is validated against the state machine and passed to `on_receive()`.

Raises `ProtocolError` if message framing is invalid. Raises `StateMachineError` if a decoded message is not valid for the current phase.

### `on_send(data) -> None`

Hook called after encoding a message. Override to add I/O (write to socket) or logging.

Default implementation does nothing.

### `on_receive(msg) -> None`

Hook called after decoding and validating a message. Override to add logging, metrics, or custom handling.

Default implementation does nothing.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `phase` | `ConnectionPhase` | Current connection phase (delegates to state machine) |
| `is_active` | `bool` | `True` if connection has not terminated or failed |
| `is_ready` | `bool` | `True` if connection is ready to accept queries |
| `pending_syncs` | `int` | Number of pending Sync responses (for pipelined extended queries) |

---

## `FrontendConnection`

Client-side connection. Uses `BackendMessageDecoder` + `FrontendStateMachine`.

```python
from pygwire import FrontendConnection

conn = FrontendConnection()
```

**Parameters:**

- `initial_phase` (`ConnectionPhase`, default `STARTUP`): Starting connection phase. Use a later phase (e.g., `READY`) for connection pooling or proxying where startup is already complete.
- `strict` (`bool`, default `True`): If `True`, state machine violations raise `StateMachineError`. If `False`, violations are logged as warnings and the connection continues.

### Client example

```python
--8<-- "examples/docs/connection_client_example.py"
```

---

## `BackendConnection`

Server-side connection. Uses `FrontendMessageDecoder` + `BackendStateMachine`.

```python
from pygwire import BackendConnection

conn = BackendConnection()
```

**Parameters:**

- `initial_phase` (`ConnectionPhase`, default `STARTUP`): Starting connection phase. Use a later phase (e.g., `READY`) for connection pooling or proxying where startup is already complete.
- `strict` (`bool`, default `True`): If `True`, state machine violations raise `StateMachineError`. If `False`, violations are logged as warnings and the connection continues.

### Server example

```python
from pygwire import BackendConnection
from pygwire import TransactionStatus
from pygwire.messages import AuthenticationOk, ReadyForQuery, StartupMessage

conn = BackendConnection()

for msg in conn.receive(client_data):
    if isinstance(msg, StartupMessage):
        client_sock.send(conn.send(AuthenticationOk()))
        client_sock.send(conn.send(ReadyForQuery(status=TransactionStatus.IDLE)))
```

---

## Subclassing for I/O

Override `on_send()` and `on_receive()` to integrate with your transport:

```python
--8<-- "examples/docs/connection_subclass_sync.py"
```

### Async example

```python
--8<-- "examples/docs/connection_subclass_async.py"
```

See the [authentication proxy example](../examples/auth-proxy.md) for a complete async proxy using this pattern.

---

## Phase tracking

The `phase` property delegates to the state machine. Use it to drive protocol loops:

```python
--8<-- "examples/docs/connection_phase_tracking.py"
```

---

## When to use Connection vs low-level API

**Use Connection when:**

- Building a client or server that follows the standard protocol flow
- You want decoder + state machine coordination without boilerplate
- You want hooks for I/O integration

**Use the low-level API when:**

- You need the decoder without state tracking (e.g., passive protocol analysis)
- You need to manipulate the decoder or state machine independently
- You are building a proxy that needs separate state machines for each side
