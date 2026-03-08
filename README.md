<div align="center">

# 🐘 pygwire 🐍

**A low-level PostgreSQL wire protocol codec for Python**

[![CI](https://github.com/DHUKK/pygwire/actions/workflows/ci.yml/badge.svg)](https://github.com/DHUKK/pygwire/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

</div>

>[!WARNING]
> **Early stage project.** Pygwire is under active development. The API is not yet stable and breaking changes should be expected between releases.

---

Pygwire is a **sans-I/O** PostgreSQL wire protocol (v3.0 and v3.2) codec. All codec and state machine logic is I/O-independent, making it portable across `asyncio`, `trio`, synchronous sockets, or any other transport.

## ✨ Features

- **Sans-I/O design.** No I/O dependencies. Bring your own transport.
- **Zero-copy parsing.** Uses `memoryview` for buffer slicing.
- **Complete protocol coverage.** All PostgreSQL v3.0 and v3.2 wire protocol messages.
- **Protocol state machines.** Validate message sequences for both client and server roles.
- **Zero dependencies.** No runtime dependencies.
- **Fully typed.** Ships with `py.typed` marker for PEP 561 support.

## 📦 Installation

```bash
pip install pygwire
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add pygwire
```

## 🚀 Quick Start

### Using Connection (recommended)

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

### Decoding server messages (client-side)

```python
from pygwire import BackendMessageDecoder

decoder = BackendMessageDecoder()
decoder.feed(data_from_server)

for msg in decoder:
    print(f"{type(msg).__name__}: {msg}")
```

### Decoding client messages (server/proxy-side)

```python
from pygwire import FrontendMessageDecoder

decoder = FrontendMessageDecoder(startup=True)
decoder.feed(data_from_client)

for msg in decoder:
    print(f"{type(msg).__name__}: {msg}")
```

### Encoding messages

```python
from pygwire.messages import Query

query = Query(query_string="SELECT * FROM users")
wire_bytes = query.to_wire()
```

### Tracking connection state

```python
from pygwire import FrontendStateMachine, ConnectionPhase
from pygwire.constants import TransactionStatus
from pygwire.messages import (
    AuthenticationOk,
    BackendKeyData,
    ParameterStatus,
    ReadyForQuery,
    StartupMessage,
)

sm = FrontendStateMachine()

sm.send(StartupMessage(params={"user": "postgres", "database": "mydb"}))
print(sm.phase)  # ConnectionPhase.AUTHENTICATING

sm.receive(AuthenticationOk())
sm.receive(ParameterStatus(name="server_version", value="15.0"))
sm.receive(BackendKeyData(process_id=1234, secret_key=b"\x00\x00\x00\x01"))
sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
print(sm.phase)  # ConnectionPhase.READY
```

## 🏗️ Architecture

Pygwire is organized into four layers, from low-level to high-level:

| Layer | Module | Purpose |
|-------|--------|---------|
| **Messages** | `pygwire.messages` | Encode and decode all PostgreSQL protocol messages |
| **Codec** | `pygwire.codec` | Incremental stream decoder with zero-copy framing |
| **State Machine** | `pygwire.state_machine` | Protocol phase tracking and message validation |
| **Connection** | `pygwire.connection` | Coordinated decoder + state machine (sans-I/O) |

Use the lower layers independently for maximum control, or use **Connection** for a higher-level API that coordinates them together.

>[!NOTE]
> Pygwire follows PostgreSQL's naming convention: **backend** = server, **frontend** = client.

## 📋 Requirements

- Python 3.11+
- No runtime dependencies

## 📚 Documentation

- [Pygwire Documentation](https://dhukk.github.io/pygwire) (full API reference and guides)
- [PostgreSQL Wire Protocol (official)](https://www.postgresql.org/docs/current/protocol.html)
- [PostgreSQL Message Formats](https://www.postgresql.org/docs/current/protocol-message-formats.html)

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.
