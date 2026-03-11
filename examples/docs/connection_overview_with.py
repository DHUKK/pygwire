"""Connection: Overview - With Connection."""

import socket

from pygwire import FrontendConnection
from pygwire.messages import StartupMessage

conn = FrontendConnection()
sock = socket.create_connection(("localhost", 5432))
startup_msg = StartupMessage(params={"user": "postgres", "database": "postgres"})

sock.send(conn.send(startup_msg))

for msg in conn.receive(sock.recv(4096)):
    # state machine is updated automatically
    print(msg)
