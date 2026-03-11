# Codec

The codec module provides incremental stream decoders that parse raw bytes into typed message objects.

## Decoders

| Decoder | Direction | Use case |
|---------|-----------|----------|
| `BackendMessageDecoder` | Server to Client | Building a client or proxy |
| `FrontendMessageDecoder` | Client to Server | Building a server or proxy |

Both share the same API.

---

## `BackendMessageDecoder`

Decoder for backend (server to client) messages.

```python
from pygwire import BackendMessageDecoder

decoder = BackendMessageDecoder()
```

**Parameters:** None

The decoder automatically uses phase-aware framing based on the current connection phase. When used standalone (without `Connection`), you must manually update the `phase` property as the connection state changes.

!!! note
    Backend messages use standard framing (identifier byte + length + payload) except during SSL/GSSAPI negotiation. The decoder handles phase transitions automatically when coordinated with `FrontendConnection`.

---

## `FrontendMessageDecoder`

Decoder for frontend (client to server) messages.

```python
from pygwire import FrontendMessageDecoder

decoder = FrontendMessageDecoder()
```

**Parameters:** None

The decoder automatically uses phase-aware framing based on the current connection phase. Startup messages (StartupMessage, SSLRequest, etc.) use identifier-less framing, while standard messages use identifier byte + length + payload.

!!! important
    When using the decoder standalone (without `BackendConnection`), you are responsible for updating the `phase` property to match connection state transitions. The `Connection` classes handle this automatically.

---

## Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `feed(data)` | `None` | Append bytes to the internal buffer and parse complete messages |
| `read()` | `PGMessage \| None` | Return next decoded message, or `None` |
| `read_all()` | `list[PGMessage]` | Drain and return all decoded messages |
| `clear()` | `None` | Discard all buffered data and pending messages |

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `phase` | `ConnectionPhase` | Current connection phase (read/write). Update this manually when using decoder standalone. |
| `buffered` | `int` | Number of unprocessed bytes in the buffer |

## Iteration

Both decoders implement `__iter__` and `__next__`:

```python
decoder.feed(raw_bytes)
for msg in decoder:
    print(type(msg).__name__)
```

---

## Basic usage

```python
--8<-- "examples/docs/codec_basic_usage.py"
```

## Streaming and partial messages

The decoder handles arbitrarily chunked input. Feed one byte at a time or megabytes at once. It buffers internally until a complete message is available:

```python
--8<-- "examples/docs/codec_streaming.py"
```

## Phase-aware framing

The PostgreSQL wire protocol uses different framing formats based on connection phase:

1. **STARTUP phase**: messages have no identifier byte (length + payload only)
2. **SSL_NEGOTIATION/GSS_NEGOTIATION**: single-byte responses
3. **Standard phases**: messages have identifier byte + length + payload

The decoder automatically selects the correct framing based on the `phase` property:

```python
--8<-- "examples/docs/codec_phase_aware.py"
```

!!! tip
    Use `FrontendConnection` or `BackendConnection` to automatically coordinate decoder phase with state machine transitions.

## Buffer management

The decoder uses `memoryview` for zero-copy payload slicing. It automatically compacts its internal buffer when consumed data exceeds 4 KB. You do not need to manage the buffer yourself.

To discard all buffered data and pending messages:

```python
decoder.clear()
```
