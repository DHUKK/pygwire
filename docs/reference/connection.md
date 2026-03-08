# pygwire.connection

Sans-I/O connection coordination classes.

## `Connection`

Abstract base class that coordinates a message decoder and state machine. Use `FrontendConnection` or `BackendConnection`.

### Methods

#### `send(msg: PGMessage) -> bytes`

Validate the message against the state machine, encode it to wire format, and call `on_send()`. Returns the wire-format bytes.

Raises `StateMachineError` if the message is not valid for the current phase.

#### `receive(data: bytes) -> Iterator[PGMessage]`

Feed raw bytes to the decoder and yield decoded messages. Each message is validated against the state machine, and `on_receive()` is called.

Raises `StateMachineError` if a decoded message is not valid for the current phase.

#### `on_send(data: bytes) -> None`

Hook called after encoding a message. Override to add I/O (e.g., write to socket) or logging.

Default implementation does nothing.

#### `on_receive(msg: PGMessage) -> None`

Hook called after decoding and validating a message. Override to add logging, metrics, or custom handling.

Default implementation does nothing.

### Properties

#### `phase -> ConnectionPhase`

Current connection phase (delegates to the underlying state machine).

#### `is_active -> bool`

`True` if the connection has not terminated or failed.

---

## `FrontendConnection`

Client-side connection. Uses `BackendMessageDecoder` to decode server messages and `FrontendStateMachine` to track client-side protocol state.

```python
from pygwire import FrontendConnection

conn = FrontendConnection()
```

---

## `BackendConnection`

Server-side connection. Uses `FrontendMessageDecoder` to decode client messages and `BackendStateMachine` to track server-side protocol state.

```python
from pygwire import BackendConnection

conn = BackendConnection(startup=True)
```

**Parameters:**

- `startup` (`bool`, default `True`): Whether to expect startup messages. Set to `False` if the connection has already completed startup (e.g., for connection pooling).
