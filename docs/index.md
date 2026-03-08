# pygwire

**A low-level PostgreSQL wire protocol codec for Python.**

[![CI](https://github.com/DHUKK/pygwire/actions/workflows/ci.yml/badge.svg)](https://github.com/DHUKK/pygwire/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

!!! warning "Early stage project"
    Pygwire is under active development. The API is not yet stable and breaking changes should be expected between releases.

---

Pygwire is a **sans-I/O** PostgreSQL wire protocol (v3.0 and v3.2) codec. All codec and state machine logic is I/O-independent, making it portable across `asyncio`, `trio`, synchronous sockets, or any other transport.

## Features

- **Sans-I/O design.** No I/O dependencies. Bring your own transport.
- **Zero-copy parsing.** Uses `memoryview` for buffer slicing.
- **Complete protocol coverage.** All PostgreSQL v3.0 and v3.2 wire protocol messages.
- **Protocol state machines.** Validate message sequences for both client and server roles.
- **Zero dependencies.** No runtime dependencies.
- **Fully typed.** Ships with `py.typed` marker for PEP 561 support.

## Architecture

Pygwire is organized into four layers, from low-level to high-level:

| Layer | Module | Purpose |
|-------|--------|---------|
| **Messages** | `pygwire.messages` | Encode and decode all PostgreSQL protocol messages |
| **Codec** | `pygwire.codec` | Incremental stream decoder with zero-copy framing |
| **State Machine** | `pygwire.state_machine` | Protocol phase tracking and message validation |
| **Connection** | `pygwire.connection` | Coordinated decoder + state machine (sans-I/O) |

Use the lower layers independently for maximum control, or use **Connection** for a higher-level API that coordinates them together.

!!! note "PostgreSQL naming convention"
    Pygwire follows PostgreSQL's naming convention: **backend** = server, **frontend** = client.

## Quick example

### Using Connection (recommended)

`FrontendConnection` coordinates a decoder and state machine together:

```python
import socket

from pygwire import FrontendConnection, ConnectionPhase
from pygwire.messages import StartupMessage, Query, DataRow

conn = FrontendConnection()
sock = socket.create_connection(("localhost", 5432))

# Send startup
sock.send(conn.send(StartupMessage(params={"user": "postgres", "database": "mydb"})))

# Handle authentication
while conn.phase != ConnectionPhase.READY:
    for msg in conn.receive(sock.recv(4096)):
        ...  # handle auth messages

# Send a query and read results
sock.send(conn.send(Query(query_string="SELECT 1")))
for msg in conn.receive(sock.recv(4096)):
    if isinstance(msg, DataRow):
        print(msg.columns)
```

### Using the low-level API

For maximum control, use the codec, messages, and state machine independently:

```python
from pygwire import BackendMessageDecoder
from pygwire.messages import Query

# Decode server messages
decoder = BackendMessageDecoder()
decoder.feed(data_from_server)
for msg in decoder:
    print(f"{type(msg).__name__}: {msg}")

# Encode client messages
query = Query(query_string="SELECT 1")
wire_bytes = query.to_wire()
```

## What is sans-I/O?

Pygwire's core never reads from or writes to sockets, files, or any other I/O source. Instead, you:

1. **Feed** raw bytes into the decoder (from whatever transport you use)
2. **Read** decoded message objects out
3. **Encode** messages to bytes and send them yourself

This means pygwire works identically with `asyncio`, `trio`, plain sockets, or even in-memory buffers for testing. The [sans-I/O manifesto](https://sans-io.readthedocs.io/) describes this pattern in detail.

The `Connection` classes follow the same principle. They coordinate protocol state internally but never perform I/O. Subclass and override `on_send()` and `on_receive()` to integrate with your transport layer:

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
conn.send(Query(query_string="SELECT 1"))  # automatically sends to socket
```
