"""Connection: Complete client example."""

import hashlib
import socket

from pygwire import messages
from pygwire.connection import FrontendConnection
from pygwire.constants import ConnectionPhase

conn = FrontendConnection()
sock = socket.create_connection(("localhost", 5432))

# Send startup
sock.send(conn.send(messages.StartupMessage(params={"user": "postgres", "database": "postgres"})))


def compute_md5_password(password: str, username: str, salt: bytes) -> str:
    inner = hashlib.md5(f"{password}{username}".encode()).hexdigest()
    outer = hashlib.md5(f"{inner}".encode() + salt).hexdigest()
    return f"md5{outer}"


# Handle authentication
while conn.phase != ConnectionPhase.READY:
    for msg in conn.receive(sock.recv(4096)):
        if isinstance(msg, messages.AuthenticationMD5Password):
            md5_hash = compute_md5_password(password="postgres", username="postgres", salt=msg.salt)
            sock.send(conn.send(messages.PasswordMessage(password=md5_hash)))
        print(msg)

# Send query and read results
sock.send(conn.send(messages.Query(query_string="SELECT 1")))
while conn.phase == ConnectionPhase.SIMPLE_QUERY:
    for msg in conn.receive(sock.recv(4096)):
        print(msg)
