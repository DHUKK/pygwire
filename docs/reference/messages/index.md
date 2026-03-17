# Messages

Pygwire provides typed classes for every message in the PostgreSQL wire protocol (v3.0 and v3.2). All messages are available from `pygwire.messages` in a flat namespace:

```python
from pygwire.messages import Query, DataRow, ReadyForQuery
```

## Message hierarchy

```
PGMessage (base)
├── FrontendMessage   (sent by clients)
├── BackendMessage    (sent by servers)
├── CommonMessage     (bidirectional, e.g. CopyData)
└── SpecialMessage    (startup-phase, no identifier byte)
```

These are primarily useful for type hints and `isinstance` checks.

## Exceptions

| Exception | Description |
|-----------|-------------|
| `PygwireError` | Base exception for all pygwire errors |
| `ProtocolError` | Wire protocol violation |

## Encoding and decoding

Every message has a `to_wire()` method that returns the complete wire-format bytes:

```python
from pygwire.messages import Query, StartupMessage

# Standard message: identifier + length + payload
query = Query(query_string="SELECT 1")
wire_bytes = query.to_wire()  # b'Q\x00\x00\x00\rSELECT 1\x00'

# Startup message: length + payload (no identifier)
startup = StartupMessage(params={"user": "postgres", "database": "mydb"})
wire_bytes = startup.to_wire()
```

Messages are typically decoded by the [codec](../codec.md), but you can also decode manually:

```python
from pygwire.messages import Query

msg = Query.decode(memoryview(b"SELECT 1\x00"))
print(msg.query_string)  # SELECT 1
```

## Messages by phase

| Phase | Messages |
|-------|----------|
| [Startup](startup.md) | `StartupMessage`, `SSLRequest`, `GSSEncRequest`, `CancelRequest` |
| [Authentication](auth.md) | `AuthenticationOk`, `AuthenticationMD5Password`, `AuthenticationSASL`, `PasswordMessage`, ... |
| [Simple Query](simple-query.md) | `Query`, `RowDescription`, `DataRow`, `CommandComplete`, `ReadyForQuery`, ... |
| [Extended Query](extended-query.md) | `Parse`, `Bind`, `Describe`, `Execute`, `Close`, `Sync`, `Flush`, ... |
| [COPY](copy.md) | `CopyData`, `CopyDone`, `CopyFail`, `CopyInResponse`, `CopyOutResponse`, ... |
| [Errors and Notices](errors.md) | `ErrorResponse`, `NoticeResponse`, `NotificationResponse`, `ParameterStatus` |
| [Miscellaneous](misc.md) | `BackendKeyData`, `FunctionCall`, `Terminate`, `NegotiateProtocolVersion` |

