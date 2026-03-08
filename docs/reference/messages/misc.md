# Miscellaneous Messages

| Message | Direction | Description |
|---------|-----------|-------------|
| `BackendKeyData` | Backend | Process ID and secret key for cancellation |
| `NegotiateProtocolVersion` | Backend | Protocol version negotiation |
| `FunctionCall` | Frontend | Server function invocation (legacy) |
| `FunctionCallResponse` | Backend | Function result |
| `Terminate` | Frontend | Close connection |

---

## `BackendKeyData`

Sent during initialization. Provides the process ID and secret key needed to construct a `CancelRequest` on a separate connection.

| Field | Type | Description |
|-------|------|-------------|
| `process_id` | `int` | Backend process ID |
| `secret_key` | `bytes` | Secret key for `CancelRequest` (4 bytes for v3.0, variable for v3.2) |

## `NegotiateProtocolVersion`

Sent when the server does not support the exact protocol version or options requested by the client.

| Field | Type | Description |
|-------|------|-------------|
| `newest_minor` | `int` | Newest minor version supported by server |
| `unrecognized` | `list[str]` | Unrecognized protocol options |

## `FunctionCall`

Legacy server function invocation. Deprecated in favor of the extended query protocol.

| Field | Type | Description |
|-------|------|-------------|
| `function_oid` | `int` | Function OID |
| `arg_formats` | `list[int]` | Argument format codes |
| `arguments` | `list[bytes \| None]` | Argument values |
| `result_format` | `int` | Result format code |

## `FunctionCallResponse`

Result of a `FunctionCall`.

| Field | Type | Description |
|-------|------|-------------|
| `result` | `bytes \| None` | Function result (`None` if the function returned NULL) |

## `Terminate`

Gracefully close the connection. No fields.

```python
from pygwire.messages import Terminate

msg = Terminate()
wire_bytes = msg.to_wire()
```
