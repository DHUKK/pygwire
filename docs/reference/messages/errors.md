# Errors, Notices, and Notifications

Messages for errors, warnings, async notifications, and runtime parameter changes.

| Message | Direction | Description |
|---------|-----------|-------------|
| `ErrorResponse` | Backend | Error with severity, code, message |
| `NoticeResponse` | Backend | Warning or informational notice |
| `NotificationResponse` | Backend | LISTEN/NOTIFY notification |
| `ParameterStatus` | Backend | Runtime parameter changed |

---

## `ErrorResponse`

| Field | Type | Description |
|-------|------|-------------|
| `fields` | `dict[str, str]` | Error fields keyed by single-char code |

Fields are keyed by single-character codes. See the [PostgreSQL error field documentation](https://www.postgresql.org/docs/current/protocol-error-fields.html) for the full list.

Convenience properties: `severity`, `code`, `message`.

## `NoticeResponse`

Same structure as `ErrorResponse`. Used for warnings and informational notices that do not terminate the current operation.

| Field | Type | Description |
|-------|------|-------------|
| `fields` | `dict[str, str]` | Notice fields keyed by single-char code |

Convenience properties: `severity`, `code`, `message`.

---

## `NotificationResponse`

Delivered asynchronously when another session sends a NOTIFY on a channel you are LISTENing to. Can arrive at any time during an active connection.

| Field | Type | Description |
|-------|------|-------------|
| `process_id` | `int` | Notifying backend PID |
| `channel` | `str` | Channel name |
| `payload` | `str` | Notification payload |

## `ParameterStatus`

Sent by the server when a runtime parameter changes (e.g. `server_version`, `client_encoding`). Also sent during the initialization phase after authentication.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Parameter name |
| `value` | `str` | Parameter value |
