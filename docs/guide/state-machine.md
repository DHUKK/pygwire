# State Machine

The state machine tracks the PostgreSQL connection lifecycle and validates that messages are sent and received in the correct order for the current protocol phase.

## Overview

There are two state machines, one for each role:

| State Machine | Role | Use case |
|---------------|------|----------|
| `FrontendStateMachine` | Client | Validate client-side protocol flow |
| `BackendStateMachine` | Server | Validate server-side protocol flow |

Both track the current `ConnectionPhase` and raise `StateMachineError` if an invalid message is sent or received.

## Basic usage

```python
from pygwire import FrontendStateMachine, ConnectionPhase
from pygwire.messages import StartupMessage, Query

sm = FrontendStateMachine()
print(sm.phase)  # ConnectionPhase.STARTUP

# Record messages as you send/receive them
sm.send(StartupMessage(params={"user": "postgres", "database": "mydb"}))
print(sm.phase)  # ConnectionPhase.AUTHENTICATING

sm.receive(auth_ok)
sm.receive(parameter_status)
sm.receive(backend_key_data)
sm.receive(ready_for_query)
print(sm.phase)  # ConnectionPhase.READY
```

## Connection phases

The `ConnectionPhase` enum tracks where you are in the protocol lifecycle:

| Phase | Description |
|-------|-------------|
| `STARTUP` | Initial state, waiting for startup message |
| `SSL_NEGOTIATION` | SSL/TLS negotiation in progress |
| `GSS_NEGOTIATION` | GSS encryption negotiation in progress |
| `AUTHENTICATING` | Authentication exchange |
| `INITIALIZATION` | Post-auth setup (ParameterStatus, BackendKeyData) |
| `READY` | Idle, ready for queries |
| `SIMPLE_QUERY` | Simple query protocol active |
| `EXTENDED_QUERY` | Extended query protocol active |
| `COPY_IN` | COPY FROM stdin active |
| `COPY_OUT` | COPY TO stdout active |
| `COPY_BOTH` | Bidirectional copy (replication) |
| `FUNCTION_CALL` | Legacy function call active |
| `TERMINATING` | Terminate message sent |
| `TERMINATED` | Connection closed |
| `FAILED` | Unrecoverable error |

## Error handling

The state machine raises `StateMachineError` when a message is invalid for the current phase:

```python
from pygwire import FrontendStateMachine
from pygwire.messages import Query
from pygwire.state_machine import StateMachineError

sm = FrontendStateMachine()

try:
    # Can't send a query before completing startup
    sm.send(Query(query_string="SELECT 1"))
except StateMachineError as e:
    print(f"Invalid: {e}")
```

## Proxy usage

A proxy needs state machines for both sides. The auth proxy example shows how to use dual state machines to validate protocol flow from both perspectives:

```python
from pygwire import FrontendStateMachine, BackendStateMachine

# Track client-side protocol flow
frontend_sm = FrontendStateMachine()

# Track server-side protocol flow
backend_sm = BackendStateMachine()

# When a client message arrives:
frontend_sm.send(client_msg)    # Client sent it
backend_sm.receive(client_msg)  # Server received it

# When a server message arrives:
backend_sm.send(server_msg)     # Server sent it
frontend_sm.receive(server_msg) # Client received it
```

Both state machines should stay in the same phase. A mismatch indicates a protocol violation.

!!! tip "Connection classes"
    If you don't need to manage the decoder and state machine separately, use `FrontendConnection` or `BackendConnection` from `pygwire.connection`. They coordinate both for you automatically. See the [Connection guide](connection.md) for details.
