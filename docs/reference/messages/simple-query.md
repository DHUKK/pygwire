# Simple Query Messages

The simple query protocol sends a SQL string and receives results in a single round trip.

| Message | Direction | Description |
|---------|-----------|-------------|
| `Query` | Frontend | SQL query string |
| `RowDescription` | Backend | Column metadata |
| `DataRow` | Backend | One row of data |
| `CommandComplete` | Backend | Query finished (includes command tag) |
| `EmptyQueryResponse` | Backend | Empty query string received |
| `ReadyForQuery` | Backend | Server ready for next command |

Typical flow:

```
Client                Server
  │                     │
  │──── Query ─────────>│
  │                     │
  │<─── RowDescription ─│
  │<─── DataRow ────────│
  │<─── DataRow ────────│
  │<─── CommandComplete ─│
  │<─── ReadyForQuery ──│
```

---

## `Query`

| Field | Type | Description |
|-------|------|-------------|
| `query_string` | `str` | SQL query text |

```python
from pygwire.messages import Query

msg = Query(query_string="SELECT * FROM users WHERE id = 1")
wire_bytes = msg.to_wire()
```

## `RowDescription`

Column metadata for the result set.

| Field | Type | Description |
|-------|------|-------------|
| `fields` | `list[FieldDescription]` | Column descriptors |

### `FieldDescription`

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Column name |
| `table_oid` | `int` | Table OID (0 if not a table column) |
| `column_attr` | `int` | Column attribute number within table |
| `type_oid` | `int` | Data type OID |
| `type_size` | `int` | Data type size (-1 for variable length) |
| `type_modifier` | `int` | Type modifier |
| `format_code` | `int` | 0 = text, 1 = binary |

## `DataRow`

One row of query results.

| Field | Type | Description |
|-------|------|-------------|
| `columns` | `list[bytes \| None]` | Column values (`None` for SQL NULL) |

```python
from pygwire.messages import DataRow

# Check results
if isinstance(msg, DataRow):
    for col in msg.columns:
        if col is None:
            print("NULL")
        else:
            print(col.decode())
```

## `CommandComplete`

Indicates the command finished successfully.

| Field | Type | Description |
|-------|------|-------------|
| `tag` | `str` | Command tag (e.g. `"SELECT 42"`, `"INSERT 0 1"`, `"DELETE 3"`) |

## `EmptyQueryResponse`

Sent when the query string is empty. No fields.

## `ReadyForQuery`

Server is ready for the next command.

| Field | Type | Description |
|-------|------|-------------|
| `status` | `TransactionStatus` | Current transaction status |

`TransactionStatus` values: `IDLE` (`"I"`), `IN_TRANSACTION` (`"T"`), `ERROR_TRANSACTION` (`"E"`).
