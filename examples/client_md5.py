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

from pygwire import BackendMessageDecoder, FrontendStateMachine
from pygwire.messages import (
    AuthenticationMD5Password,
    AuthenticationOk,
    DataRow,
    PasswordMessage,
    Query,
    ReadyForQuery,
    StartupMessage,
    Terminate,
)
from pygwire.state_machine import ConnectionPhase


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


sock = socket.create_connection(("localhost", 5432))
decoder = BackendMessageDecoder()
sm = FrontendStateMachine()

# 1. Send startup
startup = StartupMessage(params={"user": "postgres", "database": "postgres"})
sock.send(startup.to_wire())
sm.send(startup)

# 2. Handle authentication
authenticated = False
while not authenticated:
    decoder.feed(sock.recv(4096))
    for msg in decoder:
        sm.receive(msg)

        if isinstance(msg, AuthenticationMD5Password):
            md5_hash = compute_md5_password("postgres", "postgres", msg.salt)
            pwd_msg = PasswordMessage(password=md5_hash)
            sock.send(pwd_msg.to_wire())
            sm.send(pwd_msg)

        elif isinstance(msg, AuthenticationOk):
            authenticated = True

        elif isinstance(msg, ReadyForQuery):
            break

    if sm.phase == ConnectionPhase.READY:
        break

# 3. Send a query
query = Query(query_string="SELECT 1 AS num")
sock.send(query.to_wire())
sm.send(query)

# 4. Read results
while True:
    decoder.feed(sock.recv(4096))
    for msg in decoder:
        sm.receive(msg)
        if isinstance(msg, DataRow):
            print(f"Result: {msg.columns}")
        if isinstance(msg, ReadyForQuery):
            break
    if sm.phase == ConnectionPhase.READY:
        break

# 5. Disconnect
sock.send(Terminate().to_wire())
sock.close()
