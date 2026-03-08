# pygwire

Top-level exports from the `pygwire` package.

## Decoders

### `BackendMessageDecoder`

::: pygwire.codec.BackendMessageDecoder

Decoder for backend (server → client) messages.

```python
BackendMessageDecoder(*, startup: bool = False)
```

**Parameters:**

- `startup`: If `True`, expect identifier-less startup messages first. Typically `False` for client-side usage.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `feed(data)` | `None` | Append bytes to the internal buffer and parse complete messages |
| `read()` | `PGMessage \| None` | Return next decoded message, or `None` |
| `read_all()` | `list[PGMessage]` | Drain and return all decoded messages |
| `clear()` | `None` | Discard all buffered data and pending messages |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `in_startup` | `bool` | `True` while expecting startup-phase messages |
| `buffered` | `int` | Number of unprocessed bytes in the buffer |

**Iteration:**

```python
for msg in decoder:
    ...  # yields PGMessage objects until buffer is empty
```

---

### `FrontendMessageDecoder`

Decoder for frontend (client → server) messages. Same API as `BackendMessageDecoder`.

```python
FrontendMessageDecoder(*, startup: bool = False)
```

For server-side usage, set `startup=True` to handle the initial startup handshake where messages lack an identifier byte.

---

## Constants

### `ProtocolVersion`

`IntEnum` of PostgreSQL protocol version codes.

| Member | Value | Description |
|--------|-------|-------------|
| `V3_0` | `0x00030000` | Standard protocol (PG 14-17) |
| `V3_2` | `0x00030002` | Extended protocol (PG 18+) |
| `SSL_REQUEST` | `80877103` | SSL negotiation |
| `CANCEL_REQUEST` | `80877102` | Cancel request |
| `GSSENC_REQUEST` | `80877104` | GSS encryption |

### `TransactionStatus`

`StrEnum` of transaction states returned in `ReadyForQuery` messages.

| Member | Value | Description |
|--------|-------|-------------|
| `IDLE` | `"I"` | Not in a transaction |
| `IN_TRANSACTION` | `"T"` | In a transaction block |
| `ERROR_TRANSACTION` | `"E"` | In a failed transaction |

---

## State Machines

### `FrontendStateMachine`

Tracks protocol state from the client's perspective.

```python
sm = FrontendStateMachine()
```

**Methods:**

| Method | Description |
|--------|-------------|
| `send(msg)` | Record sending a message; validates it's legal for current phase |
| `receive(msg)` | Record receiving a message; validates it's legal for current phase |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `phase` | `ConnectionPhase` | Current connection phase |

### `BackendStateMachine`

Tracks protocol state from the server's perspective. Same API as `FrontendStateMachine`.

### `ConnectionPhase`

`Enum` of connection lifecycle phases. See [State Machine guide](../guide/state-machine.md#connection-phases) for the full list.

### `StateMachineError`

Raised when an invalid message is sent or received for the current phase. Subclass of `ProtocolError`.

---

## Connections

The connection classes coordinate a decoder and state machine together, providing a higher-level sans-I/O API.

### `Connection`

Abstract base class. Use `FrontendConnection` or `BackendConnection`.

**Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `send(msg)` | `bytes` | Validate via state machine, encode to wire format, call `on_send()` hook |
| `receive(data)` | `Iterator[PGMessage]` | Feed bytes to decoder, validate each message, call `on_receive()` hook |
| `on_send(data)` | `None` | Hook called after encoding. Override to add I/O |
| `on_receive(msg)` | `None` | Hook called after decoding. Override to add logging/metrics |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `phase` | `ConnectionPhase` | Current connection phase (delegates to state machine) |
| `is_active` | `bool` | `True` if connection is not terminated or failed |

### `FrontendConnection`

Client-side connection. Uses `BackendMessageDecoder` + `FrontendStateMachine`.

```python
from pygwire import FrontendConnection

conn = FrontendConnection()
```

### `BackendConnection`

Server-side connection. Uses `FrontendMessageDecoder` + `BackendStateMachine`.

```python
from pygwire import BackendConnection

conn = BackendConnection(startup=True)
```

**Parameters:**

- `startup`: Whether to expect startup messages (default `True`). Set to `False` if the connection has already completed startup.

### Subclassing for I/O

Override `on_send()` and `on_receive()` to integrate with your transport:

```python
class SocketConnection(FrontendConnection):
    def __init__(self, sock):
        super().__init__()
        self.sock = sock

    def on_send(self, data: bytes) -> None:
        self.sock.send(data)

    def on_receive(self, msg: PGMessage) -> None:
        print(f"Received: {type(msg).__name__}")
```
