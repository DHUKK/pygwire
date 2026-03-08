# Extended Query Messages

The extended query protocol separates parsing, binding, and execution into distinct steps. Supports prepared statements, parameterized queries, and pipelining.

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

Typical flow:

```
Client                    Server
  │                         │
  │──── Parse ─────────────>│
  │──── Bind ──────────────>│
  │──── Describe (Portal) ─>│
  │──── Execute ───────────>│
  │──── Sync ──────────────>│
  │                         │
  │<─── ParseComplete ──────│
  │<─── BindComplete ───────│
  │<─── RowDescription ─────│
  │<─── DataRow ────────────│
  │<─── CommandComplete ────│
  │<─── ReadyForQuery ──────│
```

---

## Frontend messages

### `Parse`

Prepare a SQL statement.

| Field | Type | Description |
|-------|------|-------------|
| `statement` | `str` | Prepared statement name (empty string = unnamed) |
| `query` | `str` | SQL query with `$1`, `$2` placeholders |
| `param_types` | `list[int]` | Parameter type OIDs (0 = let server infer) |

```python
from pygwire.messages import Parse

msg = Parse(statement="", query="SELECT $1::int", param_types=[0])
```

### `Bind`

Bind parameter values to a prepared statement, creating a portal.

| Field | Type | Description |
|-------|------|-------------|
| `portal` | `str` | Portal name (empty string = unnamed) |
| `statement` | `str` | Prepared statement name |
| `param_formats` | `list[int]` | Parameter format codes (0 = text, 1 = binary) |
| `param_values` | `list[bytes \| None]` | Parameter values (`None` for NULL) |
| `result_formats` | `list[int]` | Result column format codes |

```python
from pygwire.messages import Bind

msg = Bind(
    portal="",
    statement="",
    param_formats=[0],
    param_values=[b"42"],
    result_formats=[0],
)
```

### `Describe`

Request metadata for a statement or portal.

| Field | Type | Description |
|-------|------|-------------|
| `kind` | `str` | `"S"` for statement, `"P"` for portal |
| `name` | `str` | Statement or portal name |

### `Execute`

Execute a portal.

| Field | Type | Description |
|-------|------|-------------|
| `portal` | `str` | Portal name |
| `max_rows` | `int` | Max rows to return (0 = unlimited) |

### `Close`

Close a statement or portal.

| Field | Type | Description |
|-------|------|-------------|
| `kind` | `str` | `"S"` for statement, `"P"` for portal |
| `name` | `str` | Statement or portal name |

### `Sync`

Marks the end of an extended query batch. The server processes all preceding messages and responds with `ReadyForQuery`. No fields.

### `Flush`

Request the server to flush its output buffer without ending the batch. No fields.

---

## Backend messages

### `ParseComplete`

Parse succeeded. No fields.

### `BindComplete`

Bind succeeded. No fields.

### `CloseComplete`

Close succeeded. No fields.

### `ParameterDescription`

Parameter type information for a prepared statement.

| Field | Type | Description |
|-------|------|-------------|
| `type_oids` | `list[int]` | Parameter type OIDs |

### `NoData`

The statement will not return rows. No fields.

### `PortalSuspended`

Portal execution was suspended (the `max_rows` limit in `Execute` was reached). No fields.
