# Authentication Proxy

This example demonstrates how to build a PostgreSQL proxy that handles authentication on behalf of clients, allowing them to connect without providing credentials.

## Overview

The authentication proxy acts as a middleman between PostgreSQL clients (like `psql`) and a real PostgreSQL server:

1. **Client → Proxy**: Clients connect using `trust` authentication (no password required)
2. **Proxy → Server**: Proxy authenticates to the real server using `MD5` or `SCRAM-SHA-256`
3. **Message Forwarding**: All messages are decoded, logged, and forwarded

## Use Cases

- **Testing**: Validate pygwire's codec and state machines for authentication flows
- **Learning**: Understand PostgreSQL authentication protocols (`MD5`, `SCRAM-SHA-256`, `trust`)
- **Debugging**: Inspect all protocol messages with full visibility
- **Middleware**: Build authentication layers or connection poolers
- **Security**: Centralize database credentials instead of distributing them to clients

## Design: Two-Phase Approach

This proxy uses a **two-phase design** that balances functionality with simplicity:

### Phase 1: Authentication (With State Machines)

During startup and authentication, the proxy actively participates in the protocol:

- **Decodes messages** to intercept and handle authentication
- **Uses state machines** to validate protocol flow and catch errors
- **Constructs messages** to send trust auth to client, real auth to server

```mermaid
flowchart LR
    Client["Client<br/>(psql)"]
    Proxy["Proxy"]
    Server["Server<br/>(Postgres)"]

    Client <-->|Trust Auth| Proxy
    Proxy <-->|MD5/SCRAM Auth| Server

    Client -.->|BackendStateMachine<br/>validates auth flow| Proxy
    Proxy -.->|FrontendStateMachine<br/>validates auth flow| Server
```

**State machine for client auth** (`BackendStateMachine`):
- Created temporarily during client authentication
- Validates message flow and catches protocol errors
- Discarded after authentication completes

**State machine for server auth** (`FrontendStateMachine`):
- Created temporarily during server authentication
- Validates message flow and catches protocol errors
- Discarded after authentication completes

### Phase 2: Query Phase (Decoding Only, No Validation)

After authentication, the proxy switches to a simpler mode:

- **Decodes and logs messages** for visibility and debugging
- **No state machine validation** - messages are logged but not validated
- **More efficient** - no validation overhead during high-volume query phase

```mermaid
flowchart LR
    Client["Client<br/>(psql)"]
    Proxy["Proxy<br/><br/><i>Decode + Log</i><br/><i>(no validation)</i>"]
    Server["Server<br/>(Postgres)"]

    Client <--> Proxy
    Proxy <--> Server
```

This design demonstrates that **state machines are most valuable during complex protocol phases** (authentication) but can be optional during straightforward phases (query/response). The logging remains valuable throughout for debugging.

## Usage

### Configuration

Configure the proxy using environment variables:

```bash
export PROXY_PORT=5433                              # Port proxy listens on
export PROXY_SERVER_HOST=localhost                  # Real PostgreSQL server
export PROXY_SERVER_PORT=5432                       # Real server port
export PROXY_SERVER_SSL=true                        # Use SSL to server
export PROXY_SERVER_USER=myuser                     # Server username
export PROXY_SERVER_PASSWORD=mypassword             # Server password
export PROXY_SERVER_DATABASE=mydb                   # Server database
```

### Running the Proxy

```bash
python examples/auth_proxy.py
```

Output:
```
11:06:54 [INFO] Proxy listening on ('0.0.0.0', 5433)
11:06:54 [INFO] Forwarding to PostgreSQL at localhost:5432
11:06:54 [INFO] Server: SSL=True, User=myuser, DB=mydb
11:06:54 [INFO] Clients will use trust auth, proxy will authenticate to server
11:06:54 [INFO] Press Ctrl+C to stop
```

### Connecting Through the Proxy

Connect with any PostgreSQL client without providing credentials:

```bash
# psql (no password needed)
psql -h localhost -p 5433 -U anyuser mydb

# Python with psycopg2
import psycopg2
conn = psycopg2.connect(
    host="localhost",
    port=5433,
    user="anyuser",
    database="mydb"
    # No password
)
```

### Example Session

```bash
$ psql -h localhost -p 5433 -U testuser testdb
psql (15.16, server 15.12)
Type "help" for help.

testdb=> SELECT version();
                                                 version
─────────────────────────────────────────────────────────────────────────
 PostgreSQL 15.12 on x86_64-pc-linux-gnu, compiled by gcc (GCC) 11.2.0
(1 row)

testdb=> \q
```

Proxy logs show all protocol messages:

```
11:07:00 [INFO] [127.0.0.1:65244] New connection from ('127.0.0.1', 65244)
11:07:00 [INFO] [127.0.0.1:65244] Server SSL response: SUPPORTED
11:07:00 [INFO] [127.0.0.1:65244] SSL handshake complete
11:07:00 [INFO] [127.0.0.1:65244] Server authenticated!
11:07:00 [INFO] [127.0.0.1:65244] Client startup: user=testuser, db=testdb
11:07:00 [INFO] [127.0.0.1:65244] Client authenticated with trust auth
11:07:05 [INFO] [127.0.0.1:65244] → Query (query="SELECT version();...")
11:07:05 [INFO] [127.0.0.1:65244] ← RowDescription
11:07:05 [INFO] [127.0.0.1:65244] ← DataRow
11:07:05 [INFO] [127.0.0.1:65244] ← CommandComplete (tag=SELECT 1)
11:07:05 [INFO] [127.0.0.1:65244] ← ReadyForQuery (status=IDLE)
```

## Implementation Details

### Key Components

**`PostgreSQLStream`** - High-level stream adapter that combines:
- Async I/O (reading from/writing to streams)
- Message decoding/encoding using pygwire's codec
- Optional state machine tracking (enabled during authentication, disabled during query phase)

**`ProxyConnection`** - Manages a single client connection:
- Connects and authenticates to real PostgreSQL server
- Handles client startup with `trust` authentication
- Proxies messages bidirectionally with decoding and logging

### SSL Negotiation

The proxy supports SSL/TLS connections to the backend server:

```python title="examples/auth_proxy.py" linenums="360"
--8<-- "examples/auth_proxy.py:360:384"
```

### Authentication

The proxy supports multiple authentication methods when connecting to the backend server:

**MD5 Password Authentication:**
```python title="examples/auth_proxy.py" linenums="394"
--8<-- "examples/auth_proxy.py:394:406"
```

**SCRAM-SHA-256 Authentication:**
```python title="examples/auth_proxy.py" linenums="407"
--8<-- "examples/auth_proxy.py:407:431"
```

During authentication, a state machine validates the protocol flow. After authentication completes, the proxy switches to decoding-only mode for better performance.

### Message Forwarding

After authentication, messages are decoded and logged but not validated by state machines:

```python title="examples/auth_proxy.py" linenums="256"
--8<-- "examples/auth_proxy.py:256:283"
```

This approach keeps the valuable logging for debugging while removing the overhead of state machine validation during the query phase.

## Source Code

The complete source code is available at [`examples/auth_proxy.py`](https://github.com/DHUKK/pygwire/blob/main/examples/auth_proxy.py).

## Further Reading

- [PostgreSQL Wire Protocol](https://www.postgresql.org/docs/current/protocol.html)
- [State Machine Guide](../guide/state-machine.md)
- [Codec Guide](../guide/codec.md)
