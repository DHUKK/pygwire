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
- **Complete protocol coverage.** All PostgreSQL v3.0 and v3.2 wire protocol messages with connection phase tracking.
- **Zero dependencies.** No runtime dependencies.
- **Fully typed.** Ships with `py.typed` marker for PEP 561 support.

## Architecture

Pygwire is organized into four layers, from low-level to high-level:

| Layer | Module | Purpose |
|-------|--------|---------|
| **Messages** | `pygwire.messages` | Encode and decode all PostgreSQL protocol messages |
| **Codec** | `pygwire.codec` | Incremental stream decoder with zero-copy framing |
| **State Machine** | `pygwire.state_machine` | Connection phase tracking for framing, disambiguation, and lifecycle |
| **Connection** | `pygwire.connection` | Coordinated decoder + state machine (sans-I/O) |

Use the lower layers independently for maximum control, or use **Connection** for a higher-level API that coordinates them together.

!!! note "PostgreSQL naming convention"
    Pygwire follows PostgreSQL's naming convention: **backend** = server, **frontend** = client.

## Quick example

### Using Connection (recommended)

`FrontendConnection` coordinates a decoder and state machine together:

```python
--8<-- "examples/docs/index_connection.py"
```

### Using the low-level API

For maximum control, use the codec, messages, and state machine independently:

```python
--8<-- "examples/docs/index_lowlevel.py"
```

## What is sans-I/O?

Pygwire's core never reads from or writes to sockets, files, or any other I/O source. Instead, you:

1. **Feed** raw bytes into the decoder (from whatever transport you use)
2. **Read** decoded message objects out
3. **Encode** messages to bytes and send them yourself

This means pygwire works identically with `asyncio`, `trio`, plain sockets, or even in-memory buffers for testing. The [sans-I/O manifesto](https://sans-io.readthedocs.io/) describes this pattern in detail.

The `Connection` classes follow the same principle. They coordinate protocol state internally but never perform I/O. Subclass and override `on_send()` and `on_receive()` to integrate with your transport layer:

```python
--8<-- "examples/docs/index_subclass.py"
```
