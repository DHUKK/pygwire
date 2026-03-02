# Codec

The codec module provides incremental stream decoders that parse raw bytes into typed message objects. This is the main entry point for most pygwire usage.

## Decoders

There are two decoders, one for each direction of the PostgreSQL protocol:

| Decoder | Direction | Use case |
|---------|-----------|----------|
| `BackendMessageDecoder` | Server → Client | Building a client or proxy |
| `FrontendMessageDecoder` | Client → Server | Building a server or proxy |

Both share the same API.

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

The decoder handles arbitrarily chunked input. You can feed one byte at a time or megabytes at once and it will buffer internally until a complete message is available:

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

The PostgreSQL wire protocol uses two different framing formats:

1. **Startup phase**: messages have no identifier byte (just length + payload)
2. **Standard phase**: messages have an identifier byte + length + payload

For server-side decoding, enable startup mode so the decoder knows to expect the identifier-less format first:

```python
from pygwire import FrontendMessageDecoder

# Server receiving client connections
decoder = FrontendMessageDecoder(startup=True)
decoder.feed(first_data_from_client)

for msg in decoder:
    # First message will be StartupMessage, SSLRequest, etc.
    # Decoder automatically switches to standard framing after StartupMessage
    print(type(msg).__name__)
```

The decoder automatically switches from startup to standard framing after receiving a `StartupMessage`.

## Properties

```python
decoder.in_startup  # True while expecting startup-phase messages
decoder.buffered    # Number of unprocessed bytes in the buffer
```

## Buffer management

The decoder uses `memoryview` for zero-copy payload slicing and automatically compacts its internal buffer when consumed data exceeds 4KB. You don't need to manage the buffer yourself.

To discard all buffered data and pending messages:

```python
decoder.clear()
```
