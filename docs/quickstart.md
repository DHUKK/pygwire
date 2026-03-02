# Quick Start

This guide walks through the core pygwire workflow: decoding messages from a byte stream, encoding messages to send, and tracking protocol state.

## Decoding server messages (client-side)

When building a PostgreSQL client, use `BackendMessageDecoder` to parse messages from the server:

```python
from pygwire import BackendMessageDecoder
from pygwire.messages import ReadyForQuery, DataRow, RowDescription

decoder = BackendMessageDecoder()

# Feed raw bytes received from the server (any chunk size)
decoder.feed(data_from_server)

# Iterate over fully decoded messages
for msg in decoder:
    if isinstance(msg, RowDescription):
        columns = [field.name for field in msg.fields]
        print(f"Columns: {columns}")
    elif isinstance(msg, DataRow):
        print(f"Row: {msg.columns}")
    elif isinstance(msg, ReadyForQuery):
        print(f"Server ready (tx status: {msg.status})")
```

The decoder handles partial messages automatically. If you feed half a message, it buffers internally until the rest arrives.

## Decoding client messages (server/proxy-side)

When building a server or proxy, use `FrontendMessageDecoder` with `startup=True` to handle the initial startup handshake:

```python
from pygwire import FrontendMessageDecoder
from pygwire.messages import StartupMessage, Query

decoder = FrontendMessageDecoder(startup=True)

decoder.feed(data_from_client)
for msg in decoder:
    if isinstance(msg, StartupMessage):
        print(f"Client connecting: user={msg.params.get('user')}")
    elif isinstance(msg, Query):
        print(f"Query: {msg.query_string}")
```

!!! info "Why `startup=True`?"
    The PostgreSQL wire protocol has two framing formats. Startup messages (like `StartupMessage`, `SSLRequest`) have no identifier byte (just a length and payload). After the startup phase, all messages use standard framing with an identifier byte. The `startup` flag tells the decoder which format to expect first.

## Encoding messages

All message classes have a `to_wire()` method that returns the complete wire-format bytes:

```python
from pygwire.messages import Query, StartupMessage, Terminate

# Simple query
query = Query(query_string="SELECT * FROM users WHERE id = 1")
socket.send(query.to_wire())

# Startup message
startup = StartupMessage(params={"user": "postgres", "database": "mydb"})
socket.send(startup.to_wire())

# Graceful disconnect
socket.send(Terminate().to_wire())
```

## Tracking connection state

The state machine validates that messages are sent and received in the correct order:

```python
from pygwire import FrontendStateMachine, ConnectionPhase
from pygwire.messages import StartupMessage, Query, ReadyForQuery

sm = FrontendStateMachine()

# Track what you send
sm.send(StartupMessage(params={"user": "postgres", "database": "mydb"}))
print(sm.phase)  # ConnectionPhase.AUTHENTICATING

# Track what you receive
sm.receive(auth_ok_from_server)
sm.receive(ready_for_query_from_server)
print(sm.phase)  # ConnectionPhase.READY

# The state machine raises StateMachineError if you
# try to send a message that's invalid for the current phase
sm.send(Query(query_string="SELECT 1"))
print(sm.phase)  # ConnectionPhase.SIMPLE_QUERY
```

## Putting it together

Here's a complete example showing decode + encode + state tracking with MD5 authentication:

```python title="examples/client_md5.py"
--8<-- "examples/client_md5.py:14:"
```

[View full example on GitHub](https://github.com/DHUKK/pygwire/blob/main/examples/client_md5.py)

!!! note "Authentication modes"
    This example uses MD5 password authentication. For SCRAM-SHA-256 or other authentication methods, see the [auth proxy example](https://github.com/DHUKK/pygwire/blob/main/examples/auth_proxy.py) for a complete implementation.

## Next steps

- [Codec guide](guide/codec.md): deep dive into the stream decoder
- [Messages guide](guide/messages.md): all message classes and their fields
- [State Machine guide](guide/state-machine.md): protocol phase tracking
- [API Reference](reference/core.md): complete API documentation
