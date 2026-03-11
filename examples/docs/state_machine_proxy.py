"""State Machine: Proxy usage."""

from pygwire import BackendStateMachine, FrontendStateMachine

frontend_sm = FrontendStateMachine()
backend_sm = BackendStateMachine()

# When a client message arrives:
# frontend_sm.send(client_msg)    # Client sent it
# backend_sm.receive(client_msg)  # Server received it

# When a server message arrives:
# backend_sm.send(server_msg)     # Server sent it
# frontend_sm.receive(server_msg) # Client received it

# Both state machines should stay in the same phase.
# A mismatch indicates a protocol violation.
