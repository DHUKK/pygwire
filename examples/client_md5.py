"""PostgreSQL client example with MD5 authentication.

This demonstrates a complete client connection with MD5 password authentication,
query execution, and graceful disconnection.

Usage:
    python examples/client_md5.py

Requirements:
    - PostgreSQL server running on localhost:5432
    - User 'postgres' with password 'postgres' and MD5 authentication enabled
"""

import hashlib
import socket
from collections.abc import Iterator

from pygwire import FrontendConnection
from pygwire.messages import (
    AuthenticationMD5Password,
    DataRow,
    PasswordMessage,
    PGMessage,
    Query,
    StartupMessage,
    Terminate,
)
from pygwire.state_machine import ConnectionPhase


# --8<-- [start:socket_connection]
class SocketConnection(FrontendConnection):
    """Example of adding I/O directly via hooks.

    This subclass overrides the hooks to automatically send/receive via socket.
    """

    def __init__(self, sock: socket.socket) -> None:
        super().__init__()
        self.sock = sock

    def on_send(self, data: bytes) -> None:
        """Automatically send data to socket."""
        self.sock.send(data)

    def recv_messages(self) -> Iterator[PGMessage]:
        """Convenience method: receive data and yield decoded messages."""
        data = self.sock.recv(4096)
        yield from self.receive(data)
# --8<-- [end:socket_connection]


# --8<-- [start:md5_hash]
def compute_md5_password(password: str, username: str, salt: bytes) -> str:
    """Compute PostgreSQL MD5 password hash.

    PostgreSQL's MD5 authentication requires:
    1. Hash the password and username: md5(password + username)
    2. Hash the result with the salt: md5(hash1 + salt)
    3. Prepend "md5" to the final hex string
    """
    inner = hashlib.md5(f"{password}{username}".encode()).hexdigest()
    outer = hashlib.md5(f"{inner}".encode() + salt).hexdigest()
    return f"md5{outer}"
# --8<-- [end:md5_hash]


# --8<-- [start:client_flow]
sock = socket.create_connection(("localhost", 5432))
conn = SocketConnection(sock)

# 1. Send startup
startup = StartupMessage(params={"user": "postgres", "database": "postgres"})
conn.send(startup)

# 2. Handle authentication
while conn.phase != ConnectionPhase.READY:
    for msg in conn.recv_messages():
        if isinstance(msg, AuthenticationMD5Password):
            md5_hash = compute_md5_password("postgres", "postgres", msg.salt)
            pwd_msg = PasswordMessage(password=md5_hash)
            conn.send(pwd_msg)

# 3. Send a query
query = Query(query_string="SELECT 1 AS num")
conn.send(query)

# 4. Read results
while conn.phase == ConnectionPhase.SIMPLE_QUERY:  # type: ignore[comparison-overlap]
    for msg in conn.recv_messages():
        if isinstance(msg, DataRow):
            print(f"Result: {msg.columns}")

# 5. Disconnect
conn.send(Terminate())
sock.close()
# --8<-- [end:client_flow]
