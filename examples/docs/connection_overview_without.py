"""Connection: Overview - Without Connection."""

import socket

from pygwire.codec import BackendMessageDecoder
from pygwire.messages import StartupMessage
from pygwire.state_machine import FrontendStateMachine

decoder = BackendMessageDecoder()
sm = FrontendStateMachine()
sock = socket.create_connection(("localhost", 5432))
startup_msg = StartupMessage(params={"user": "postgres", "database": "postgres"})

sm.send(startup_msg)  # Update the state machine
decoder.phase = sm.phase  # Sync decoder with state machine
sock.send(startup_msg.to_wire())

decoder.feed(sock.recv(4096))
for msg in decoder:
    sm.receive(msg)  # Update the state machine
    decoder.phase = sm.phase  # Sync decoder with state machine
    print(msg)
