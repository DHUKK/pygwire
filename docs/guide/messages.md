# Messages

Pygwire provides typed classes for every message in the PostgreSQL wire protocol (v3.0 and v3.2). All messages are available from `pygwire.messages` in a flat namespace.

## Message hierarchy

```
PGMessage (base)
├── FrontendMessage   (sent by clients)
├── BackendMessage    (sent by servers)
├── CommonMessage     (bidirectional, e.g. CopyData)
└── SpecialMessage    (startup-phase, no identifier byte)
```

## Encoding messages

Every message has a `to_wire()` method that returns the complete wire-format bytes:

```python
from pygwire.messages import Query, StartupMessage

# Standard message: identifier + length + payload
query = Query(query_string="SELECT 1")
wire_bytes = query.to_wire()  # b'Q\x00\x00\x00\rSELECT 1\x00'

# Startup message: length + payload (no identifier)
startup = StartupMessage(params={"user": "postgres", "database": "mydb"})
wire_bytes = startup.to_wire()  # b'\x00\x00\x00%\x00\x03\x00\x00user\x00postgres\x00database\x00mydb\x00\x00'
```

## Decoding messages

Messages are typically decoded by the [codec](codec.md), but you can also decode manually:

```python
from pygwire.messages import Query

# Decode from a memoryview payload (after framing is stripped)
msg = Query.decode(memoryview(b'SELECT 1\x00'))
print(msg.query_string)  # SELECT 1
```

## Messages by protocol phase

### Startup

| Message | Direction | Description |
|---------|-----------|-------------|
| `StartupMessage` | Frontend | Connection initialization with parameters |
| `SSLRequest` | Frontend | Request SSL/TLS negotiation |
| `GSSEncRequest` | Frontend | Request GSS encryption |
| `CancelRequest` | Frontend | Cancel a running query |

### Authentication

| Message | Direction | Description |
|---------|-----------|-------------|
| `SSLResponse` | Backend | Response to SSL negotiation |
| `AuthenticationOk` | Backend | Authentication successful |
| `AuthenticationCleartextPassword` | Backend | Request cleartext password |
| `AuthenticationMD5Password` | Backend | Request MD5 password (includes salt) |
| `AuthenticationSASL` | Backend | Start SASL authentication |
| `AuthenticationSASLContinue` | Backend | SASL challenge data |
| `AuthenticationSASLFinal` | Backend | SASL completion data |
| `AuthenticationGSS` | Backend | Request GSS authentication |
| `AuthenticationGSSContinue` | Backend | GSS continuation data |
| `AuthenticationSSPI` | Backend | Request SSPI authentication |
| `AuthenticationKerberosV5` | Backend | Request Kerberos V5 (legacy) |
| `PasswordMessage` | Frontend | Password response |
| `SASLInitialResponse` | Frontend | SASL initial response |
| `SASLResponse` | Frontend | SASL continuation response |

### Simple query protocol

| Message | Direction | Description |
|---------|-----------|-------------|
| `Query` | Frontend | SQL query string |
| `RowDescription` | Backend | Column metadata |
| `DataRow` | Backend | One row of data |
| `CommandComplete` | Backend | Query finished (includes tag like `SELECT 1`) |
| `EmptyQueryResponse` | Backend | Empty query string received |
| `ReadyForQuery` | Backend | Server ready for next command |

`RowDescription` contains a list of `FieldDescription` objects with column metadata (name, type OID, etc.).

### Extended query protocol

| Message | Direction | Description |
|---------|-----------|-------------|
| `Parse` | Frontend | Prepare a statement |
| `ParseComplete` | Backend | Parse succeeded |
| `Bind` | Frontend | Bind parameters to a statement |
| `BindComplete` | Backend | Bind succeeded |
| `Describe` | Frontend | Request metadata for statement/portal |
| `ParameterDescription` | Backend | Parameter type OIDs |
| `Execute` | Frontend | Execute a portal |
| `Close` | Frontend | Close a statement/portal |
| `CloseComplete` | Backend | Close succeeded |
| `Sync` | Frontend | Synchronization point |
| `Flush` | Frontend | Flush output buffer |
| `NoData` | Backend | No rows will be returned |
| `PortalSuspended` | Backend | Portal execution suspended |

### COPY protocol

| Message | Direction | Description |
|---------|-----------|-------------|
| `CopyInResponse` | Backend | Ready for COPY IN data |
| `CopyOutResponse` | Backend | Starting COPY OUT data |
| `CopyBothResponse` | Backend | Bidirectional copy (replication) |
| `CopyData` | Both | COPY data chunk |
| `CopyDone` | Both | COPY complete |
| `CopyFail` | Frontend | Abort COPY with error |

### Errors and notices

| Message | Direction | Description |
|---------|-----------|-------------|
| `ErrorResponse` | Backend | Error with severity, code, message, etc. |
| `NoticeResponse` | Backend | Warning or informational notice |

Both `ErrorResponse` and `NoticeResponse` have a `fields` dict with keys like `'S'` (severity), `'M'` (message), `'C'` (SQLSTATE code).

### Notifications and status

| Message | Direction | Description |
|---------|-----------|-------------|
| `NotificationResponse` | Backend | LISTEN/NOTIFY notification |
| `ParameterStatus` | Backend | Runtime parameter changed |

### Miscellaneous

| Message | Direction | Description |
|---------|-----------|-------------|
| `BackendKeyData` | Backend | Process ID and secret key for cancellation |
| `NegotiateProtocolVersion` | Backend | Protocol version negotiation |
| `FunctionCall` | Frontend | Server function invocation (legacy) |
| `FunctionCallResponse` | Backend | Function result |
| `Terminate` | Frontend | Close connection |

## Lookup functions

For advanced use cases, you can look up message classes by their wire identifier:

```python
from pygwire.messages import lookup_backend, lookup_frontend, lookup_special

# Look up by single-byte identifier
msg_cls = lookup_backend(b"T")    # RowDescription
msg_cls = lookup_frontend(b"Q")   # Query

# Look up startup messages by version code
msg_cls = lookup_special(0x00030000)  # StartupMessage (v3.0)
```
