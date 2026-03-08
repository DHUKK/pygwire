# COPY Messages

Messages used during the COPY protocol for bulk data transfer.

| Message | Direction | Description |
|---------|-----------|-------------|
| `CopyInResponse` | Backend | Ready for COPY IN data |
| `CopyOutResponse` | Backend | Starting COPY OUT data |
| `CopyBothResponse` | Backend | Bidirectional copy (streaming replication) |
| `CopyData` | Both | COPY data chunk |
| `CopyDone` | Both | COPY complete |
| `CopyFail` | Frontend | Abort COPY with error |

---

## Backend messages

### `CopyInResponse`

Server is ready to receive COPY data from the client.

| Field | Type | Description |
|-------|------|-------------|
| `overall_format` | `int` | Overall format (0 = text, 1 = binary) |
| `col_formats` | `list[int]` | Per-column format codes |

### `CopyOutResponse`

Server is about to send COPY data to the client.

| Field | Type | Description |
|-------|------|-------------|
| `overall_format` | `int` | Overall format (0 = text, 1 = binary) |
| `col_formats` | `list[int]` | Per-column format codes |

### `CopyBothResponse`

Bidirectional COPY mode (used in streaming replication).

| Field | Type | Description |
|-------|------|-------------|
| `overall_format` | `int` | Overall format (0 = text, 1 = binary) |
| `col_formats` | `list[int]` | Per-column format codes |

---

## Bidirectional messages

### `CopyData`

A chunk of COPY data. Sent by the client during COPY IN, by the server during COPY OUT, and by both during COPY BOTH.

| Field | Type | Description |
|-------|------|-------------|
| `data` | `bytes` | COPY data chunk |

### `CopyDone`

Signals that COPY data transfer is complete. No fields.

---

## Frontend messages

### `CopyFail`

Client aborts the COPY operation with an error.

| Field | Type | Description |
|-------|------|-------------|
| `error_message` | `str` | Error message |
