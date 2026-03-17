# Startup Messages

These are `SpecialMessage` subclasses. They have no identifier byte and use a length-only framing format. The decoder handles this automatically when `startup=True`.

| Message | Direction | Description |
|---------|-----------|-------------|
| `StartupMessage` | Frontend | Connection initialization with parameters |
| `SSLRequest` | Frontend | Request SSL/TLS negotiation |
| `GSSEncRequest` | Frontend | Request GSS encryption |
| `CancelRequest` | Frontend | Cancel a running query |

---

## `StartupMessage`

Connection initialization. Sent as the first message from a client.

| Field | Type | Description |
|-------|------|-------------|
| `params` | `dict[str, str]` | Key-value parameters (`user`, `database`, etc.) |
| `protocol_version` | `int` | Startup request code (default: `StartupRequestCode.V3_0`) |

```python
from pygwire.messages import StartupMessage

msg = StartupMessage(params={"user": "postgres", "database": "mydb"})
wire_bytes = msg.to_wire()
```

## `SSLRequest`

Request SSL/TLS negotiation. No fields.

```python
from pygwire.messages import SSLRequest

msg = SSLRequest()
wire_bytes = msg.to_wire()
```

## `GSSEncRequest`

Request GSS encryption. No fields.

## `CancelRequest`

Cancel a running query on a different connection. Requires the process ID and secret key from `BackendKeyData`.

| Field | Type | Description |
|-------|------|-------------|
| `process_id` | `int` | Backend process ID |
| `secret_key` | `bytes` | Secret key from `BackendKeyData` |

```python
from pygwire.messages import CancelRequest

msg = CancelRequest(process_id=1234, secret_key=b"\x00\x00\x00\x01")
wire_bytes = msg.to_wire()
```
