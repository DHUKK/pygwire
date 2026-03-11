"""Connection: Phase tracking."""

import socket

from pygwire import ConnectionPhase, FrontendConnection
from pygwire.messages import Query, StartupMessage

conn = FrontendConnection()
sock = socket.create_connection(("localhost", 5432))

# Send startup
startup_msg = StartupMessage(params={"user": "postgres", "database": "postgres"})
sock.send(conn.send(startup_msg))

# Authentication loop (Using trust auth)
while conn.phase != ConnectionPhase.READY:
    for msg in conn.receive(sock.recv(4096)):
        print(msg)
        print(conn.phase)

# Query loop
sock.send(conn.send(Query(query_string="SELECT 1")))
while conn.phase == ConnectionPhase.SIMPLE_QUERY:
    for msg in conn.receive(sock.recv(4096)):
        print(msg)
        print(conn.phase)
