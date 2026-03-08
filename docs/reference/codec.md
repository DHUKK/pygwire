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

decoder = BackendMessageDecoder(*, max_message_size=1073741824)
```

**Parameters:**

- `max_message_size` (`int`, default 1 GB): Maximum allowed message size in bytes. Raises `ProtocolError` if a message declares a length exceeding this value.

!!! note
    `BackendMessageDecoder` has no `startup` parameter. Backend messages always use standard framing (identifier byte + length + payload).

---

## `FrontendMessageDecoder`

Decoder for frontend (client to server) messages.

```python
from pygwire import FrontendMessageDecoder

decoder = FrontendMessageDecoder(*, startup=False, max_message_size=1073741824)
```

**Parameters:**

- `startup` (`bool`, default `False`): If `True`, expect identifier-less startup messages first. The decoder switches to standard framing automatically after receiving a `StartupMessage`.
- `max_message_size` (`int`, default 1 GB): Maximum allowed message size in bytes.

For server-side usage, set `startup=True` to handle the initial startup handshake where messages lack an identifier byte.

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
| `in_startup` | `bool` | `True` while expecting startup-phase messages |
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
from pygwire import BackendMessageDecoder

decoder = BackendMessageDecoder()

# Feed bytes from your transport layer
decoder.feed(raw_bytes)

# Read messages one at a time
msg = decoder.read()

# Or iterate over all available messages
for msg in decoder:
    print(type(msg).__name__)

# Or drain all at once
messages = decoder.read_all()
```

## Streaming and partial messages

The decoder handles arbitrarily chunked input. Feed one byte at a time or megabytes at once. It buffers internally until a complete message is available:

```python
decoder = BackendMessageDecoder()

# These three feeds together form one complete message
decoder.feed(first_chunk)
decoder.feed(second_chunk)
decoder.feed(third_chunk)

# Now the complete message is available
msg = decoder.read()
```

## Startup mode

The PostgreSQL wire protocol uses two framing formats:

1. **Startup phase**: messages have no identifier byte (length + payload only)
2. **Standard phase**: messages have an identifier byte + length + payload

For server-side decoding, enable startup mode:

```python
from pygwire import FrontendMessageDecoder

decoder = FrontendMessageDecoder(startup=True)
decoder.feed(first_data_from_client)

for msg in decoder:
    # First message will be StartupMessage, SSLRequest, etc.
    # Decoder switches to standard framing after StartupMessage
    print(type(msg).__name__)
```

## Buffer management

The decoder uses `memoryview` for zero-copy payload slicing. It automatically compacts its internal buffer when consumed data exceeds 4 KB. You do not need to manage the buffer yourself.

To discard all buffered data and pending messages:

```python
decoder.clear()
```
