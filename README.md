<div align="center">

# 🐘 pygwire 🐍

**A low-level PostgreSQL wire protocol codec for Python**

[![CI](https://github.com/DHUKK/pygwire/actions/workflows/ci.yml/badge.svg)](https://github.com/DHUKK/pygwire/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI](https://img.shields.io/pypi/v/pygwire)](https://pypi.org/project/pygwire/)

</div>

>[!NOTE]
> **Beta.** Pygwire is under active development. The API may change between minor releases until 1.0. See the [changelog](CHANGELOG.md) for migration notes.

---

Pygwire is a **sans-I/O** PostgreSQL wire protocol (v3.0 and v3.2) codec. All codec and state machine logic is I/O-independent, making it portable across `asyncio`, `trio`, synchronous sockets, or any other transport.

## ✨ Features

- **Sans-I/O design.** No I/O dependencies. Bring your own transport.
- **Zero-copy parsing.** Uses `memoryview` for buffer slicing.
- **Complete protocol coverage.** All PostgreSQL v3.0 and v3.2 wire protocol messages with connection phase tracking.
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

**[📖 Read the full documentation →](https://dhukk.github.io/pygwire)**

```python
from pygwire import FrontendConnection
from pygwire.messages import StartupMessage, Query

conn = FrontendConnection()
sock.send(conn.send(StartupMessage(params={"user": "postgres", "database": "mydb"})))

# Authentication, queries, and more - see the docs!
```

## 🏗️ Architecture

Pygwire is organized into four layers, from low-level to high-level:

| Layer | Module | Purpose |
|-------|--------|---------|
| **Messages** | `pygwire.messages` | Encode and decode all PostgreSQL protocol messages |
| **Codec** | `pygwire.codec` | Incremental stream decoder with zero-copy framing |
| **State Machine** | `pygwire.state_machine` | Connection phase tracking for framing, disambiguation, and lifecycle |
| **Connection** | `pygwire.connection` | Coordinated decoder + state machine (sans-I/O) |

Use the lower layers independently for maximum control, or use **Connection** for a higher-level API that coordinates them together.

>[!NOTE]
> Pygwire follows PostgreSQL's naming convention: **backend** = server, **frontend** = client.

## 📋 Requirements

- Python 3.11+
- No runtime dependencies

## 📚 Documentation

**[📖 Full documentation, tutorials, and API reference →](https://dhukk.github.io/pygwire)**

### Additional Resources

- [PostgreSQL Wire Protocol (official)](https://www.postgresql.org/docs/current/protocol.html)
- [PostgreSQL Message Formats](https://www.postgresql.org/docs/current/protocol-message-formats.html)

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.
