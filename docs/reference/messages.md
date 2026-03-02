# pygwire.messages

All message classes are available from `pygwire.messages` in a flat namespace:

```python
from pygwire.messages import Query, DataRow, ReadyForQuery
```

## Base classes

These are primarily useful for type hints and `isinstance` checks.

| Class | Description |
|-------|-------------|
| `PGMessage` | Base for all messages |
| `FrontendMessage` | Messages sent by clients |
| `BackendMessage` | Messages sent by servers |
| `CommonMessage` | Bidirectional messages (COPY) |
| `SpecialMessage` | Startup-phase messages (no identifier byte) |

## Exceptions

| Exception | Description |
|-----------|-------------|
| `PygwireError` | Base exception for all pygwire errors |
| `ProtocolError` | Wire protocol violation |

## Startup messages

### `StartupMessage`

Connection initialization.

| Field | Type | Description |
|-------|------|-------------|
| `params` | `dict[str, str]` | Key-value parameters (`user`, `database`, etc.) |

### `SSLRequest`

Request SSL/TLS negotiation. No fields.

### `GSSEncRequest`

Request GSS encryption. No fields.

### `CancelRequest`

Cancel a running query.

| Field | Type | Description |
|-------|------|-------------|
| `process_id` | `int` | Backend process ID |
| `secret_key` | `bytes` | Secret key from `BackendKeyData` |

## Authentication messages

### `SSLResponse`

Single-byte response to SSL negotiation. Not a standard message; use `SSLResponse.from_bytes()`.

| Value | Name | Meaning |
|-------|------|---------|
| `b"S"` | `SUPPORTED` | Server supports SSL |
| `b"N"` | `NOT_SUPPORTED` | Server does not support SSL |

### `AuthenticationOk`

Authentication successful. No fields.

### `AuthenticationCleartextPassword`

Server requests a cleartext password. No fields.

### `AuthenticationMD5Password`

Server requests an MD5-hashed password.

| Field | Type | Description |
|-------|------|-------------|
| `salt` | `bytes` | 4-byte salt for MD5 hash |

### `AuthenticationSASL`

Server requests SASL authentication.

| Field | Type | Description |
|-------|------|-------------|
| `mechanisms` | `list[str]` | Supported SASL mechanisms |

### `AuthenticationSASLContinue`

SASL challenge data from server.

| Field | Type | Description |
|-------|------|-------------|
| `data` | `bytes` | SASL challenge bytes |

### `AuthenticationSASLFinal`

SASL completion data from server.

| Field | Type | Description |
|-------|------|-------------|
| `data` | `bytes` | SASL final bytes |

### `PasswordMessage`

Password response from client.

| Field | Type | Description |
|-------|------|-------------|
| `password` | `bytes \| str` | Password (cleartext or MD5-hashed) |

### `SASLInitialResponse`

| Field | Type | Description |
|-------|------|-------------|
| `mechanism` | `str` | SASL mechanism name |
| `response` | `bytes` | Initial response data |

### `SASLResponse`

| Field | Type | Description |
|-------|------|-------------|
| `response` | `bytes` | SASL response data |

## Simple query messages

### `Query`

| Field | Type | Description |
|-------|------|-------------|
| `query_string` | `str` | SQL query text |

### `RowDescription`

| Field | Type | Description |
|-------|------|-------------|
| `fields` | `list[FieldDescription]` | Column metadata |

### `FieldDescription`

Column metadata within a `RowDescription`.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Column name |
| `table_oid` | `int` | Table OID (0 if not a table column) |
| `column_index` | `int` | Column index within table |
| `type_oid` | `int` | Data type OID |
| `type_size` | `int` | Data type size (-1 for variable) |
| `type_modifier` | `int` | Type modifier |
| `format_code` | `int` | 0 = text, 1 = binary |

### `DataRow`

| Field | Type | Description |
|-------|------|-------------|
| `values` | `list[bytes \| None]` | Column values (`None` for SQL NULL) |

### `CommandComplete`

| Field | Type | Description |
|-------|------|-------------|
| `tag` | `str` | Command tag (e.g. `"SELECT 1"`, `"INSERT 0 1"`) |

### `EmptyQueryResponse`

Empty query string received. No fields.

### `ReadyForQuery`

| Field | Type | Description |
|-------|------|-------------|
| `status` | `TransactionStatus` | Current transaction status |

## Extended query messages

### `Parse`

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Prepared statement name (empty = unnamed) |
| `query` | `str` | SQL query with `$1`, `$2` placeholders |
| `param_types` | `list[int]` | Parameter type OIDs (0 = unspecified) |

### `Bind`

| Field | Type | Description |
|-------|------|-------------|
| `portal` | `str` | Portal name (empty = unnamed) |
| `statement` | `str` | Prepared statement name |
| `param_formats` | `list[int]` | Parameter format codes |
| `param_values` | `list[bytes \| None]` | Parameter values |
| `result_formats` | `list[int]` | Result column format codes |

### `Describe`

| Field | Type | Description |
|-------|------|-------------|
| `kind` | `bytes` | `b"S"` for statement, `b"P"` for portal |
| `name` | `str` | Statement or portal name |

### `Execute`

| Field | Type | Description |
|-------|------|-------------|
| `portal` | `str` | Portal name |
| `max_rows` | `int` | Max rows to return (0 = unlimited) |

### `Close`

| Field | Type | Description |
|-------|------|-------------|
| `kind` | `bytes` | `b"S"` for statement, `b"P"` for portal |
| `name` | `str` | Statement or portal name |

### `Sync`

Synchronization point. No fields.

### `Flush`

Request server to flush output. No fields.

### `ParseComplete`, `BindComplete`, `CloseComplete`, `NoData`, `PortalSuspended`

Completion acknowledgements. No fields.

### `ParameterDescription`

| Field | Type | Description |
|-------|------|-------------|
| `type_oids` | `list[int]` | Parameter type OIDs |

## COPY messages

### `CopyInResponse` / `CopyOutResponse` / `CopyBothResponse`

| Field | Type | Description |
|-------|------|-------------|
| `format` | `int` | Overall format (0 = text, 1 = binary) |
| `column_formats` | `list[int]` | Per-column format codes |

### `CopyData`

| Field | Type | Description |
|-------|------|-------------|
| `data` | `bytes` | COPY data chunk |

### `CopyDone`

COPY complete. No fields.

### `CopyFail`

| Field | Type | Description |
|-------|------|-------------|
| `message` | `str` | Error message |

## Error and notice messages

### `ErrorResponse` / `NoticeResponse`

| Field | Type | Description |
|-------|------|-------------|
| `fields` | `dict[str, str]` | Error/notice fields |

Common field keys:

| Key | Meaning |
|-----|---------|
| `S` | Severity (`ERROR`, `FATAL`, `WARNING`, etc.) |
| `V` | Severity (non-localized) |
| `C` | SQLSTATE error code |
| `M` | Message text |
| `D` | Detail |
| `H` | Hint |

## Notification and status messages

### `NotificationResponse`

| Field | Type | Description |
|-------|------|-------------|
| `process_id` | `int` | Notifying backend PID |
| `channel` | `str` | Channel name |
| `payload` | `str` | Notification payload |

### `ParameterStatus`

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Parameter name |
| `value` | `str` | Parameter value |

## Miscellaneous messages

### `BackendKeyData`

| Field | Type | Description |
|-------|------|-------------|
| `process_id` | `int` | Backend process ID |
| `secret_key` | `bytes` | Secret key for `CancelRequest` |

### `NegotiateProtocolVersion`

| Field | Type | Description |
|-------|------|-------------|
| `minor_version` | `int` | Newest minor version supported |
| `unrecognized` | `list[str]` | Unrecognized protocol options |

### `FunctionCall`

Legacy server function invocation.

| Field | Type | Description |
|-------|------|-------------|
| `function_oid` | `int` | Function OID |
| `arg_formats` | `list[int]` | Argument format codes |
| `args` | `list[bytes \| None]` | Argument values |
| `result_format` | `int` | Result format code |

### `FunctionCallResponse`

| Field | Type | Description |
|-------|------|-------------|
| `result` | `bytes \| None` | Function result |

### `Terminate`

Close connection. No fields.

## Lookup functions

```python
lookup_backend(identifier: bytes) -> type[BackendMessage] | None
lookup_frontend(identifier: bytes) -> type[FrontendMessage] | None
lookup_special(version_code: int) -> type[SpecialMessage] | None
```

Look up a message class by its wire protocol identifier. Returns `None` if no message matches.
