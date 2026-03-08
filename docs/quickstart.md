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
from pygwire.messages import Query

query = Query(query_string="SELECT 1")
print(query.to_wire())  # Raw wire protocol bytes
```

---

## Decoding server messages (client-side)

Use `BackendMessageDecoder` to parse messages from a PostgreSQL server:

```python
from pygwire import BackendMessageDecoder
from pygwire.messages import AuthenticationOk

decoder = BackendMessageDecoder()

# Feed raw bytes received from the server
decoder.feed(AuthenticationOk().to_wire())

# Iterate over decoded messages
for msg in decoder:
    print(f"Decoded: {type(msg).__name__}")  # "Decoded: AuthenticationOk"
```

The decoder handles partial messages automatically. If you feed half a message, it buffers internally until the rest arrives.

## Decoding client messages (server/proxy-side)

Use `FrontendMessageDecoder` with `startup=True` to handle the initial startup handshake:

```python
from pygwire import FrontendMessageDecoder
from pygwire.messages import StartupMessage, Query

decoder = FrontendMessageDecoder(startup=True)

# Simulate a client sending a startup message
startup = StartupMessage(params={"user": "postgres", "database": "mydb"})
decoder.feed(startup.to_wire())

for msg in decoder:
    if isinstance(msg, StartupMessage):
        print(f"Client connecting: user={msg.params.get('user')}")

# After startup, the decoder switches to standard framing automatically
query = Query(query_string="SELECT 1")
decoder.feed(query.to_wire())

for msg in decoder:
    if isinstance(msg, Query):
        print(f"Query: {msg.query_string}")
```

!!! info "Why `startup=True`?"
    The PostgreSQL wire protocol has two framing formats. Startup messages (`StartupMessage`, `SSLRequest`) have no identifier byte. After the startup phase, all messages use standard framing with an identifier byte. The `startup` flag tells the decoder which format to expect first.

## Encoding messages

All message classes have a `to_wire()` method that returns the complete wire-format bytes:

```python
from pygwire.messages import Query, StartupMessage, Terminate

# Simple query
query = Query(query_string="SELECT * FROM users WHERE id = 1")
print(f"Query wire bytes: {query.to_wire()!r}")

# Startup message
startup = StartupMessage(params={"user": "postgres", "database": "mydb"})
print(f"Startup wire bytes ({len(startup.to_wire())} bytes)")

# Graceful disconnect
terminate = Terminate()
print(f"Terminate wire bytes: {terminate.to_wire()!r}")
```

## Tracking connection state

The state machine validates that messages are sent and received in the correct order:

```python
from pygwire import FrontendStateMachine, ConnectionPhase
from pygwire.constants import TransactionStatus
from pygwire.messages import (
    AuthenticationOk,
    BackendKeyData,
    ParameterStatus,
    Query,
    ReadyForQuery,
    StartupMessage,
)

sm = FrontendStateMachine()

# Track what you send
sm.send(StartupMessage(params={"user": "postgres", "database": "mydb"}))
print(sm.phase)  # ConnectionPhase.AUTHENTICATING

# Track what you receive
sm.receive(AuthenticationOk())
sm.receive(ParameterStatus(name="server_version", value="15.0"))
sm.receive(BackendKeyData(process_id=1234, secret_key=b"\x00\x00\x00\x01"))
sm.receive(ReadyForQuery(status=TransactionStatus.IDLE))
print(sm.phase)  # ConnectionPhase.READY

# Raises StateMachineError for messages invalid in the current phase
sm.send(Query(query_string="SELECT 1"))
print(sm.phase)  # ConnectionPhase.SIMPLE_QUERY
```

## Using Connection (decoder + state machine together)

The `Connection` class coordinates a decoder and state machine into a single object. This removes the boilerplate of managing them separately:

```python
from pygwire import FrontendConnection, ConnectionPhase
from pygwire.constants import TransactionStatus
from pygwire.messages import (
    AuthenticationOk,
    BackendKeyData,
    ParameterStatus,
    Query,
    ReadyForQuery,
    StartupMessage,
)

conn = FrontendConnection()

# send() validates via state machine and returns wire bytes
wire_bytes = conn.send(StartupMessage(params={"user": "postgres", "database": "mydb"}))
print(conn.phase)  # ConnectionPhase.AUTHENTICATING

# receive() feeds bytes to decoder, validates each message, and yields them
server_data = (
    AuthenticationOk().to_wire()
    + ParameterStatus(name="server_version", value="15.0").to_wire()
    + BackendKeyData(process_id=1234, secret_key=b"\x00\x00\x00\x01").to_wire()
    + ReadyForQuery(status=TransactionStatus.IDLE).to_wire()
)
for msg in conn.receive(server_data):
    print(f"Received: {type(msg).__name__}")

print(conn.phase)  # ConnectionPhase.READY
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
