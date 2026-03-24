# Framing

The framing layer sits between the raw byte stream and the message decoder. It knows how to extract a single PostgreSQL wire protocol message from a buffer, accounting for the three distinct framing modes the protocol uses.

!!! note "Advanced use"
    The codec (`BackendMessageDecoder` / `FrontendMessageDecoder`) handles framing automatically. Most users never need to use this module directly. It is primarily useful for building custom decoders, protocol analyzers, or testing infrastructure.

## Overview

PostgreSQL uses different framing depending on where in the connection lifecycle a message appears:

| Framing | When used | Wire format |
|---------|-----------|-------------|
| `StartupFraming` | `STARTUP` phase, frontend | `Int32(length)` + payload |
| `NegotiationFraming` | `SSL_NEGOTIATION` / `GSS_NEGOTIATION`, backend | Single byte |
| `StandardFraming` | All other phases | `Byte1(identifier)` + `Int32(length)` + payload |

`lookup_framing(phase, direction)` selects the correct strategy automatically.

---

## `FramingStrategy`

Abstract base class for all framing strategies.

```python
from pygwire.framing import FramingStrategy
```

**Constructor parameter:**

- `max_message_size` (`int`, default `1073741824`): Maximum allowed message size in bytes. Defaults to 1 GB (PostgreSQL's `PQ_LARGE_MESSAGE_LIMIT`).

### `try_parse(buf, pos, phase, direction)`

Try to extract one message starting at position `pos` in `buf`.

- Returns `(message, bytes_consumed)` if a complete message is available.
- Returns `None` if there is not enough data yet (caller should buffer and retry).
- Raises `FramingError` if framing is malformed (bad size, unknown identifier, truncation).

---

## `StartupFraming`

Used for messages in the `STARTUP` phase (frontend direction).

**Wire format:** `Int32(length)` + payload

The length field is 4 bytes and includes itself. The first 4 bytes of the payload contain a request code that identifies the message type.

```
Bytes 0–3:  Int32 length (includes these 4 bytes)
Bytes 4–7:  Int32 request_code (identifies message type)
Bytes 8+:   Remaining payload
```

Raises `FramingError` if the request code is unknown or the payload is too short.

Messages using this framing: `StartupMessage`, `SSLRequest`, `GSSEncRequest`, `CancelRequest`.

---

## `NegotiationFraming`

Used for SSL/GSS negotiation responses (`SSL_NEGOTIATION` and `GSS_NEGOTIATION` phases, backend direction).

**Wire format:** Single byte with no length field and no identifier.

The byte value itself is the complete message:

| Byte | Meaning |
|------|---------|
| `b"S"` | SSL accepted |
| `b"N"` | SSL or GSS rejected |
| `b"G"` | GSS encryption accepted |

Raises `FramingError` if the byte is not a recognized negotiation byte for the current phase.

Messages using this framing: `SSLResponse`, `GSSResponse`.

---

## `StandardFraming`

Used for all messages after the initial handshake (the default for all other phase/direction combinations).

**Wire format:** `Byte1(identifier)` + `Int32(length)` + payload

The length field is 4 bytes. It includes itself but **not** the identifier byte. Total wire size is `1 + length` bytes.

```
Byte 0:     Identifier (e.g. b'Q' for Query, b'Z' for ReadyForQuery)
Bytes 1–4:  Int32 length (includes these 4 bytes, not the identifier)
Bytes 5+:   Payload
```

Raises `FramingError` if the identifier is unknown for the current phase and direction.

---

## `lookup_framing(phase, direction)`

```python
--8<-- "examples/docs/framing_lookup.py"
```

Returns the registered `FramingStrategy` for the given `(phase, direction)` pair, or `StandardFraming` as the default for all unlisted combinations.

| Phase | Direction | Strategy |
|-------|-----------|----------|
| `STARTUP` | `FRONTEND` | `StartupFraming` |
| `SSL_NEGOTIATION` | `BACKEND` | `NegotiationFraming` |
| `GSS_NEGOTIATION` | `BACKEND` | `NegotiationFraming` |
| (all others) | (any) | `StandardFraming` |

---

## Max message size

All framing strategies enforce a maximum message size. The default is **1 GB** (`1073741824` bytes), matching PostgreSQL's `PQ_LARGE_MESSAGE_LIMIT`. A `FramingError` is raised if a length field exceeds this limit.

To use a custom limit, instantiate the strategy directly:

```python
from pygwire.framing import StandardFraming

framing = StandardFraming(max_message_size=16 * 1024 * 1024)  # 16 MB
```
