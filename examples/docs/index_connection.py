"""Index: Using Connection (recommended).

This example will run if you have a PostgreSQL server running on localhost:5432
with trust authentication configured for the 'postgres' user.
"""

import socket

from pygwire.connection import FrontendConnection
from pygwire.constants import ConnectionPhase
from pygwire.messages import DataRow, Query, StartupMessage

conn = FrontendConnection()
sock = socket.create_connection(("localhost", 5432))

# Send startup
sock.send(conn.send(StartupMessage(params={"user": "postgres", "database": "postgres"})))

# Handle authentication (requires trust auth)
while conn.phase != ConnectionPhase.READY:
    for msg in conn.receive(sock.recv(4096)):
        print(msg)  # handle auth messages

# Send a query and read results
sock.send(conn.send(Query(query_string="SELECT 1")))
for msg in conn.receive(sock.recv(4096)):
    if isinstance(msg, DataRow):
        print(msg.columns)
