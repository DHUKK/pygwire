# Constants

Protocol-level enums and constants.

## `ConnectionPhase`

`Enum` of connection lifecycle phases. Used by state machines and decoders to track protocol flow.

| Member | Description |
|--------|-------------|
| `STARTUP` | Initial state, waiting for startup message |
| `SSL_NEGOTIATION` | SSL/TLS negotiation in progress |
| `GSS_NEGOTIATION` | GSS encryption negotiation in progress |
| `AUTHENTICATING` | Authentication exchange active |
| `AUTHENTICATING_SASL_INITIAL` | SASL authentication initial response |
| `AUTHENTICATING_SASL_CONTINUE` | SASL authentication continuation |
| `INITIALIZATION` | Post-auth setup (ParameterStatus, BackendKeyData) |
| `READY` | Idle, ready for queries |
| `SIMPLE_QUERY` | Simple query protocol active |
| `EXTENDED_QUERY` | Extended query protocol active |
| `COPY_IN` | COPY FROM stdin active |
| `COPY_OUT` | COPY TO stdout active |
| `FUNCTION_CALL` | Legacy function call active |
| `TERMINATED` | Connection closed |
| `FAILED` | Unrecoverable error |

## `MessageDirection`

`StrEnum` indicating which side sends a message type.

| Member | Value | Description |
|--------|-------|-------------|
| `FRONTEND` | `"frontend"` | Message sent by client |
| `BACKEND` | `"backend"` | Message sent by server |

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

