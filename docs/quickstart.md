# Quick Start

## Installation

Requires Python 3.11+. No runtime dependencies.

=== "pip"

    ```bash
    pip install pygwire
    ```

=== "uv"

    ```bash
    uv add pygwire
    ```

=== "poetry"

    ```bash
    poetry add pygwire
    ```

=== "From source"

    ```bash
    git clone https://github.com/DHUKK/pygwire.git
    cd pygwire
    pip install .
    ```

Verify the installation:

```python
--8<-- "examples/docs/quickstart_verify.py"
```

---

## Decoding server messages (client-side)

Use `BackendMessageDecoder` to parse messages from a PostgreSQL server:

```python
--8<-- "examples/docs/quickstart_decode_backend.py"
```

The decoder handles partial messages automatically. If you feed half a message, it buffers internally until the rest arrives.

## Decoding client messages (server/proxy-side)

Use `FrontendMessageDecoder` to decode incoming client messages. The decoder is phase-aware and handles different framing modes automatically:

```python
--8<-- "examples/docs/quickstart_decode_frontend.py"
```

!!! info "Phase-aware decoding"
    The PostgreSQL wire protocol uses different framing modes depending on the connection phase. The decoder's `phase` property determines how messages are parsed. When using the decoder standalone, you must update the phase property after each state transition. The `Connection` classes handle this automatically.

## Encoding messages

All message classes have a `to_wire()` method that returns the complete wire-format bytes:

```python
--8<-- "examples/docs/quickstart_encode.py"
```

## Tracking connection state

The state machine validates that messages are sent and received in the correct order:

```python
--8<-- "examples/docs/quickstart_state_machine.py"
```

## Using Connection (decoder + state machine together)

The `Connection` class coordinates a decoder and state machine into a single object. This removes the boilerplate of managing them separately:

```python
--8<-- "examples/docs/quickstart_connection.py"
```

Subclass and override `on_send()` / `on_receive()` to integrate with your transport. See the [Connection reference](reference/connection.md) for details.

## Complete example

A client connection with MD5 authentication using `FrontendConnection`:

```python
--8<-- "examples/client_md5.py:client_flow"
```

This uses a `SocketConnection` subclass that sends data via `on_send()`:

```python
--8<-- "examples/client_md5.py:socket_connection"
```

And the MD5 hash helper:

```python
--8<-- "examples/client_md5.py:md5_hash"
```

[View full example on GitHub](https://github.com/DHUKK/pygwire/blob/main/examples/client_md5.py)

!!! note "Authentication modes"
    This example uses MD5 password authentication. For SCRAM-SHA-256 or other methods, see the [authentication proxy example](examples/auth-proxy.md).

## Next steps

- [Connection](reference/connection.md): coordinated decoder + state machine
- [Codec](reference/codec.md): stream decoder details
- [Messages](reference/messages/index.md): all message classes and fields
- [State Machine](reference/state-machine.md): protocol phase tracking
- [Constants](reference/constants.md): enums and identifiers
