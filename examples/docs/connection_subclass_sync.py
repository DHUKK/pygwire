"""Connection: Subclassing for I/O - synchronous."""

import socket

from pygwire import ConnectionPhase, FrontendConnection
from pygwire.messages import PGMessage, Query, StartupMessage


class SocketConnection(FrontendConnection):
    def __init__(self, sock: socket.socket) -> None:
        super().__init__()
        self.sock = sock

    def on_send(self, data: bytes) -> None:
        self.sock.send(data)

    def on_receive(self, msg: PGMessage) -> None:
        print(f"Received: {msg}")


sock = socket.create_connection(("localhost", 5432))
conn = SocketConnection(sock)
conn.send(StartupMessage(params={"user": "postgres", "database": "postgres"}))
while conn.phase != ConnectionPhase.READY:
    for _ in conn.receive(sock.recv(4096)):
        ...

conn.send(Query(query_string="SELECT 1"))  # automatically sends to socket

for _ in conn.receive(sock.recv(4096)):
    pass
