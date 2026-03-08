# Authentication Messages

Messages exchanged during the authentication phase. The server sends authentication requests (backend). The client responds with credentials (frontend).

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

---

## Backend messages

### `SSLResponse`

Single-byte response to SSL negotiation. This is an `Enum`, not a standard message class.

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
| `mechanisms` | `list[str]` | Supported SASL mechanisms (e.g. `["SCRAM-SHA-256"]`) |

### `AuthenticationSASLContinue`

SASL challenge from server.

| Field | Type | Description |
|-------|------|-------------|
| `data` | `bytes` | SASL challenge bytes |

### `AuthenticationSASLFinal`

SASL completion from server.

| Field | Type | Description |
|-------|------|-------------|
| `data` | `bytes` | SASL final bytes |

### `AuthenticationGSS`

Server requests GSS authentication. No fields.

### `AuthenticationGSSContinue`

GSS continuation data from server.

| Field | Type | Description |
|-------|------|-------------|
| `data` | `bytes` | GSS continuation data |

### `AuthenticationSSPI`

Server requests SSPI authentication. No fields.

### `AuthenticationKerberosV5`

Legacy, deprecated. No fields.

---

## Frontend messages

### `PasswordMessage`

Client password response. Used for cleartext, MD5, and as a transport for SASL/GSSAPI binary data.

| Field | Type | Description |
|-------|------|-------------|
| `password` | `str \| bytes` | Password (cleartext string, MD5-hashed string, or SASL/GSSAPI binary data) |

```python
from pygwire.messages import PasswordMessage

# Cleartext
msg = PasswordMessage(password="mypassword")

# MD5 (pre-hashed)
msg = PasswordMessage(password="md5abc123...")
```

### `SASLInitialResponse`

SASL initial response from client.

| Field | Type | Description |
|-------|------|-------------|
| `mechanism` | `str` | SASL mechanism name (e.g. `"SCRAM-SHA-256"`) |
| `data` | `bytes` | Initial response data |

### `SASLResponse`

SASL continuation response from client.

| Field | Type | Description |
|-------|------|-------------|
| `data` | `bytes` | SASL response data |
