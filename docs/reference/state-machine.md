# pygwire.state_machine

Protocol state tracking and message validation.

## `FrontendStateMachine`

Tracks the connection lifecycle from the client's perspective.

```python
from pygwire.state_machine import FrontendStateMachine

sm = FrontendStateMachine()
```

### Methods

#### `send(msg: PGMessage) -> None`

Record sending a message. Raises `StateMachineError` if the message is not valid for the current phase.

#### `receive(msg: PGMessage) -> None`

Record receiving a message. Raises `StateMachineError` if the message is not valid for the current phase.

### Properties

#### `phase -> ConnectionPhase`

The current connection phase.

---

## `BackendStateMachine`

Tracks the connection lifecycle from the server's perspective. Same API as `FrontendStateMachine`.

```python
from pygwire.state_machine import BackendStateMachine

sm = BackendStateMachine()
```

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

```python
try:
    sm.send(Query(query_string="SELECT 1"))
except StateMachineError as e:
    print(f"Can't send query in phase {sm.phase}: {e}")
```
