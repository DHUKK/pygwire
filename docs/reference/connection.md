# Connection

The `Connection` classes coordinate a decoder and state machine together, providing a higher-level sans-I/O API for the PostgreSQL wire protocol.

## Overview

Without Connection, you manage a decoder and state machine separately:

```python
from pygwire import BackendMessageDecoder, FrontendStateMachine

decoder = BackendMessageDecoder()
sm = FrontendStateMachine()

sm.send(startup_msg)
sock.send(startup_msg.to_wire())

decoder.feed(sock.recv(4096))
for msg in decoder:
    sm.receive(msg)
```

With Connection, both are coordinated in a single object:

```python
from pygwire import FrontendConnection

conn = FrontendConnection()

sock.send(conn.send(startup_msg))

for msg in conn.receive(sock.recv(4096)):
    ...  # state machine is updated automatically
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

---

## `FrontendConnection`

Client-side connection. Uses `BackendMessageDecoder` + `FrontendStateMachine`.

```python
from pygwire import FrontendConnection

conn = FrontendConnection()
```

No constructor parameters.

### Client example

```python
import socket

from pygwire import FrontendConnection, ConnectionPhase
from pygwire.messages import (
    AuthenticationMD5Password,
    DataRow,
    PasswordMessage,
    Query,
    StartupMessage,
)

conn = FrontendConnection()
sock = socket.create_connection(("localhost", 5432))

# Send startup
sock.send(conn.send(StartupMessage(params={"user": "postgres", "database": "mydb"})))

# Handle authentication
while conn.phase != ConnectionPhase.READY:
    for msg in conn.receive(sock.recv(4096)):
        if isinstance(msg, AuthenticationMD5Password):
            sock.send(conn.send(PasswordMessage(password=md5_hash)))

# Send query and read results
sock.send(conn.send(Query(query_string="SELECT 1")))
while conn.phase == ConnectionPhase.SIMPLE_QUERY:
    for msg in conn.receive(sock.recv(4096)):
        if isinstance(msg, DataRow):
            print(msg.columns)
```

---

## `BackendConnection`

Server-side connection. Uses `FrontendMessageDecoder` + `BackendStateMachine`.

```python
from pygwire import BackendConnection

conn = BackendConnection(startup=True)
```

**Parameters:**

- `startup` (`bool`, default `True`): Whether to expect startup messages. Set to `False` if the connection has already completed startup (e.g., for connection pooling).

### Server example

```python
from pygwire import BackendConnection
from pygwire.constants import TransactionStatus
from pygwire.messages import AuthenticationOk, ReadyForQuery, StartupMessage

conn = BackendConnection(startup=True)

for msg in conn.receive(client_data):
    if isinstance(msg, StartupMessage):
        client_sock.send(conn.send(AuthenticationOk()))
        client_sock.send(conn.send(ReadyForQuery(status=TransactionStatus.IDLE)))
```

---

## Subclassing for I/O

Override `on_send()` and `on_receive()` to integrate with your transport:

```python
import socket

from pygwire import FrontendConnection
from pygwire.messages import PGMessage, Query

class SocketConnection(FrontendConnection):
    def __init__(self, sock: socket.socket) -> None:
        super().__init__()
        self.sock = sock

    def on_send(self, data: bytes) -> None:
        self.sock.send(data)

    def on_receive(self, msg: PGMessage) -> None:
        print(f"Received: {type(msg).__name__}")

conn = SocketConnection(sock)
conn.send(Query(query_string="SELECT 1"))  # sends to socket automatically
```

### Async example

```python
import asyncio
from collections.abc import AsyncIterator

from pygwire import FrontendConnection
from pygwire.messages import PGMessage

class AsyncConnection(FrontendConnection):
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        super().__init__()
        self._reader = reader
        self._writer = writer

    def on_send(self, data: bytes) -> None:
        self._writer.write(data)

    async def send_message(self, msg: PGMessage) -> None:
        self.send(msg)
        await self._writer.drain()

    async def recv_messages(self) -> AsyncIterator[PGMessage]:
        data = await self._reader.read(8192)
        if not data:
            return
        for msg in self.receive(data):
            yield msg
```

See the [authentication proxy example](../examples/auth-proxy.md) for a complete async proxy using this pattern.

---

## Phase tracking

The `phase` property delegates to the state machine. Use it to drive protocol loops:

```python
# Authentication loop
while conn.phase != ConnectionPhase.READY:
    for msg in conn.receive(sock.recv(4096)):
        ...

# Query loop
sock.send(conn.send(Query(query_string="SELECT 1")))
while conn.phase == ConnectionPhase.SIMPLE_QUERY:
    for msg in conn.receive(sock.recv(4096)):
        ...
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
