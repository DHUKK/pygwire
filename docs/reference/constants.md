# pygwire.constants

Protocol-level enums and constants.

## `ProtocolVersion`

`IntEnum` of PostgreSQL protocol version codes. Used in `StartupMessage` and special request messages.

| Member | Value | Description |
|--------|-------|-------------|
| `V3_0` | `0x00030000` | Standard protocol (PostgreSQL 7.4+) |
| `V3_2` | `0x00030002` | Extended protocol with variable-length cancel keys (PostgreSQL 18+) |
| `SSL_REQUEST` | `80877103` | SSL/TLS negotiation request |
| `CANCEL_REQUEST` | `80877102` | Query cancellation request |
| `GSSENC_REQUEST` | `80877104` | GSS encryption request |

## `TransactionStatus`

`StrEnum` of transaction status indicators returned in `ReadyForQuery` messages.

| Member | Value | Description |
|--------|-------|-------------|
| `IDLE` | `"I"` | Not in a transaction |
| `IN_TRANSACTION` | `"T"` | In a transaction block |
| `ERROR_TRANSACTION` | `"E"` | In a failed transaction block |

## `FrontendMessageType`

`StrEnum` of single-byte identifiers for client → server messages.

| Member | Value | Description |
|--------|-------|-------------|
| `BIND` | `"B"` | Bind parameters to statement |
| `CLOSE` | `"C"` | Close statement or portal |
| `COPY_DATA` | `"d"` | COPY data chunk |
| `COPY_DONE` | `"c"` | COPY complete |
| `COPY_FAIL` | `"f"` | Abort COPY |
| `DESCRIBE` | `"D"` | Describe statement or portal |
| `EXECUTE` | `"E"` | Execute portal |
| `FLUSH` | `"H"` | Flush output |
| `FUNCTION_CALL` | `"F"` | Legacy function call |
| `PARSE` | `"P"` | Parse SQL statement |
| `PASSWORD` | `"p"` | Password / SASL response |
| `QUERY` | `"Q"` | Simple query |
| `SYNC` | `"S"` | Synchronization point |
| `TERMINATE` | `"X"` | Close connection |

## `BackendMessageType`

`StrEnum` of single-byte identifiers for server → client messages.

| Member | Value | Description |
|--------|-------|-------------|
| `AUTHENTICATION` | `"R"` | Authentication request/response |
| `BACKEND_KEY_DATA` | `"K"` | Process ID and secret key |
| `BIND_COMPLETE` | `"2"` | Bind succeeded |
| `CLOSE_COMPLETE` | `"3"` | Close succeeded |
| `COMMAND_COMPLETE` | `"C"` | Command finished |
| `COPY_DATA` | `"d"` | COPY data chunk |
| `COPY_DONE` | `"c"` | COPY complete |
| `COPY_IN_RESPONSE` | `"G"` | Ready for COPY IN |
| `COPY_OUT_RESPONSE` | `"H"` | Starting COPY OUT |
| `COPY_BOTH_RESPONSE` | `"W"` | Bidirectional copy |
| `DATA_ROW` | `"D"` | Result row |
| `EMPTY_QUERY_RESPONSE` | `"I"` | Empty query |
| `ERROR_RESPONSE` | `"E"` | Error |
| `FUNCTION_CALL_RESPONSE` | `"V"` | Function result |
| `NEGOTIATE_PROTOCOL_VERSION` | `"v"` | Version negotiation |
| `NO_DATA` | `"n"` | No data to return |
| `NOTICE_RESPONSE` | `"N"` | Warning or notice |
| `NOTIFICATION_RESPONSE` | `"A"` | Async notification |
| `PARAMETER_DESCRIPTION` | `"t"` | Parameter type info |
| `PARAMETER_STATUS` | `"S"` | Runtime parameter |
| `PARSE_COMPLETE` | `"1"` | Parse succeeded |
| `PORTAL_SUSPENDED` | `"s"` | Portal suspended |
| `READY_FOR_QUERY` | `"Z"` | Ready for next command |
| `ROW_DESCRIPTION` | `"T"` | Column metadata |
