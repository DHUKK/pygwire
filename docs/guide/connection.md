# Connection

The `Connection` classes coordinate a decoder and state machine together, providing a higher-level sans-I/O API for the PostgreSQL wire protocol.

## Overview

When using pygwire's low-level API, you manage a decoder and state machine separately:

```python
# Low-level: manage decoder + state machine yourself
decoder = BackendMessageDecoder()
sm = FrontendStateMachine()

sm.send(startup_msg)
sock.send(startup_msg.to_wire())

decoder.feed(sock.recv(4096))
for msg in decoder:
    sm.receive(msg)
```

The `Connection` classes combine these into a single object:

```python
# Higher-level: connection coordinates both
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

## Basic usage

### Client (FrontendConnection)

```python
from pygwire import FrontendConnection, ConnectionPhase
from pygwire.messages import StartupMessage, Query, DataRow

conn = FrontendConnection()
sock = socket.create_connection(("localhost", 5432))

# Send startup
sock.send(conn.send(StartupMessage(params={"user": "postgres", "database": "mydb"})))

# Handle authentication using conn.phase
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

### Server (BackendConnection)

```python
from pygwire import BackendConnection
from pygwire.messages import AuthenticationOk, ReadyForQuery

conn = BackendConnection(startup=True)

# Receive and handle client startup
for msg in conn.receive(client_data):
    if isinstance(msg, StartupMessage):
        client_sock.send(conn.send(AuthenticationOk()))
        client_sock.send(conn.send(ReadyForQuery(status=TransactionStatus.IDLE)))
```

## Hooks for I/O integration

The connection classes are sans-I/O by default. `send()` returns bytes and `receive()` accepts bytes. To integrate with your transport layer, subclass and override `on_send()` and `on_receive()`:

```python
class SocketConnection(FrontendConnection):
    def __init__(self, sock):
        super().__init__()
        self.sock = sock

    def on_send(self, data: bytes) -> None:
        """Called after encoding. Writes to socket automatically."""
        self.sock.send(data)

    def on_receive(self, msg: PGMessage) -> None:
        """Called after decoding. Add logging, metrics, etc."""
        print(f"Received: {type(msg).__name__}")

conn = SocketConnection(sock)
conn.send(Query(query_string="SELECT 1"))  # sends to socket automatically
```

### Async example

```python
class AsyncConnection(FrontendConnection):
    def __init__(self, reader, writer):
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

## Phase tracking

The `phase` property delegates to the underlying state machine, so you can use it to drive protocol loops:

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

## When to use Connection vs low-level API

**Use `Connection` when:**

- Building a client or server that follows the standard protocol flow
- You want decoder + state machine coordination without boilerplate
- You want hooks for I/O integration

**Use the low-level API when:**

- You need to use the decoder without state tracking (e.g., passive protocol analysis)
- You need to manipulate the decoder or state machine independently
- You're building a proxy that needs separate state machines for each side
