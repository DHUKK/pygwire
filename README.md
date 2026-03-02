<div align="center">

# 🐘 pygwire 🐍

**A low-level PostgreSQL wire protocol codec for Python**

[![CI](https://github.com/DHUKK/pygwire/actions/workflows/ci.yml/badge.svg)](https://github.com/DHUKK/pygwire/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

</div>

---

Pygwire is a **sans-I/O** PostgreSQL wire protocol (v3.0 & v3.2) codec. All codec and state machine logic is completely I/O-independent, making it portable across `asyncio`, `trio`, synchronous sockets, or any other transport.

## ✨ Features

- 🔌 **Sans-I/O design** — no I/O dependencies; bring your own transport
- ⚡ **Zero-copy framing** — uses `memoryview` for buffer slicing; decoded messages own their data
- 📦 **Complete protocol coverage** — all PostgreSQL v3.0 and v3.2 wire protocol messages
- 🤖 **Protocol state machines** — validate message sequences for both client and server roles
- 🪶 **Zero dependencies** — no runtime dependencies
- 🏷️ **Fully typed** — ships with `py.typed` marker for PEP 561 support

## 📦 Installation

```bash
pip install pygwire
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add pygwire
```

## 🚀 Quick Start

### Decoding server messages (client-side)

```python
from pygwire import BackendMessageDecoder

# Create a decoder for your PostgreSQL client
decoder = BackendMessageDecoder()

# Feed raw bytes received from the server
decoder.feed(data)

# Iterate over decoded messages
for msg in decoder:
    print(f"{type(msg).__name__}: {msg}")
```

### Decoding client messages (server-side)

```python
from pygwire import FrontendMessageDecoder

# Create a decoder for your PostgreSQL server
decoder = FrontendMessageDecoder(startup=True)

# Feed raw bytes received from the client
decoder.feed(data)

# Iterate over decoded messages
for msg in decoder:
    print(f"{type(msg).__name__}: {msg}")
```

### Encoding messages

```python
from pygwire.messages import Query

# Build a simple query message
query = Query(query_string="SELECT * FROM users")

# Get wire-format bytes ready to send
wire_bytes = query.to_wire()
socket.send(wire_bytes)
```

### Tracking connection state

```python
from pygwire import FrontendStateMachine
from pygwire.messages import StartupMessage, PasswordMessage

sm = FrontendStateMachine()

# Validate that messages are legal in the current protocol phase
sm.send(StartupMessage(parameters={"user": "postgres", "database": "mydb"}))
sm.receive(auth_challenge_from_server)
sm.send(PasswordMessage(password=b"secret"))
sm.receive(ready_for_query_from_server)

print(sm.phase)  # ConnectionPhase.READY
```

## 🏗️ Architecture

Pygwire is organized into three layers:

| Layer | Module | Purpose |
|-------|--------|---------|
| **Messages** | `pygwire.messages` | Encode/decode all PostgreSQL protocol messages |
| **Codec** | `pygwire.codec` | Incremental stream decoder with zero-copy framing |
| **State Machine** | `pygwire.state_machine` | Protocol phase tracking and message validation |

>[!NOTE]
> Pygwire follows PostgreSQL's naming convention — `backend` = `server`, `frontend` = `client`.

## 📋 Requirements

- Python 3.11+

## 📚 Documentation

- [Pygwire Documentation](https://dhukk.github.io/pygwire) — Full API reference and guides
- [PostgreSQL Wire Protocol (official)](https://www.postgresql.org/docs/current/protocol.html)
- [Protocol Message Formats](https://www.postgresql.org/docs/current/protocol-message-formats.html)

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

