"""PostgreSQL Authentication Proxy Example

This example demonstrates how to build a PostgreSQL proxy that handles authentication
on behalf of clients, allowing them to connect without providing credentials.

## What It Does

The proxy acts as a middleman between PostgreSQL clients (like psql) and a real
PostgreSQL server:

1. **Client → Proxy**: Clients connect using trust authentication (no password required)
2. **Proxy → Server**: Proxy authenticates to the real server using MD5 or SCRAM-SHA-256
3. **Message Forwarding**: All messages are decoded, logged, and forwarded

## Design Note

This proxy uses **two distinct phases**:

### Authentication Phase (Uses State Machines)
- **Decodes messages** to actively participate in authentication
- **Uses state machines** to track and validate the authentication flow
- **Constructs messages** to send trust auth to client and real auth to server

### Query Phase (Decoding Only, No State Tracking)
- **Decodes and logs messages** for visibility and debugging
- **No state machine validation** - messages are logged but not validated
- **More efficient** - validation overhead removed after authentication

This design demonstrates that state machines are most valuable during complex
protocol phases (authentication) but can be optional during straightforward
phases (query/response). The logging remains valuable throughout.

## Use Cases

- Testing pygwire's codec and state machine for authentication flows
- Understanding PostgreSQL authentication protocols (SSL, MD5, SCRAM-SHA-256)
- Debugging protocol interactions with full message visibility
- Building authentication middleware or connection poolers
- Centralizing database credentials

## Usage

Configure via environment variables:

    export PROXY_PORT=5433
    export PROXY_SERVER_HOST=localhost
    export PROXY_SERVER_PORT=5432
    export PROXY_SERVER_SSL=true
    export PROXY_SERVER_USER=myuser
    export PROXY_SERVER_PASSWORD=mypassword
    export PROXY_SERVER_DATABASE=mydb

Run the proxy:

    python examples/auth_proxy.py

Connect through the proxy (no password needed!):

    psql -h localhost -p 5433 -U anyuser mydb

The proxy handles all authentication with the real server, so clients can connect
without providing credentials. All protocol messages are logged for inspection.
"""

import asyncio
import logging
import os
import ssl
import sys

from pygwire import codec, messages
from pygwire.constants import TransactionStatus
from pygwire.state_machine import BackendStateMachine, FrontendStateMachine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class PostgreSQLStream:
    """High-level stream adapter that handles reading/writing PostgreSQL messages with state tracking.

    This combines:
    - Async I/O (reading from/writing to streams)
    - Message decoding/encoding
    - Automatic state machine tracking for the local side

    This makes proxy code much simpler - just call read_message() and send_message().
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        decoder: codec.FrontendMessageDecoder | codec.BackendMessageDecoder,
        state_machine: FrontendStateMachine | BackendStateMachine | None = None,
        connection_id: str = "unknown",
    ):
        """Initialize a PostgreSQL stream.

        Args:
            reader: Async stream reader for incoming data
            writer: Async stream writer for outgoing data
            decoder: Message decoder (Frontend or Backend)
            state_machine: State machine for tracking our side of the connection (optional)
            connection_id: Connection identifier for logging (optional)
        """
        self.reader = reader
        self.writer = writer
        self._decoder = decoder
        self._state_machine = state_machine
        self._connection_id = connection_id

    async def read_message(self) -> messages.PGMessage | None:
        """Read and decode next message from stream with automatic state tracking.

        Returns None if stream is closed.
        """
        msg = self._read_buffered()
        if msg is not None:
            return msg

        data = await self.reader.read(8192)
        if not data:
            return None

        self._decoder.feed(data)
        return self._read_buffered()

    def _read_buffered(self) -> messages.PGMessage | None:
        """Read next buffered message and track in state machine.

        When reading from stream, we receive the message from the remote side.
        """
        msg = self._decoder.read()
        if msg is None:
            return None

        if self._state_machine is not None:
            self._state_machine.receive(msg)  # type: ignore[arg-type]

        return msg

    async def send_message(self, msg: messages.PGMessage) -> None:
        """Encode and send message to stream with automatic state tracking.

        When sending to stream, we are sending the message to the remote side.
        """
        if self._state_machine is not None:
            self._state_machine.send(msg)  # type: ignore[arg-type]

        self.writer.write(msg.to_wire())
        await self.writer.drain()

    async def forward_raw(self, data: bytes) -> None:
        """Forward raw bytes to stream (for transparent proxying)."""
        self.writer.write(data)
        await self.writer.drain()


class ProxyConnection:
    """Handles a single client connection, proxying to the PostgreSQL server.

    Uses state machines during authentication phase for validation, then switches
    to decoding-only mode (with logging) for the query phase.
    """

    def __init__(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        server_host: str,
        server_port: int,
        server_ssl: bool = False,
        server_user: str | None = None,
        server_password: str | None = None,
        server_database: str | None = None,
    ):
        self.client_reader = client_reader
        self.client_writer = client_writer
        self.server_host = server_host
        self.server_port = server_port
        self.server_ssl = server_ssl
        self.server_user = server_user
        self.server_password = server_password
        self.server_database = server_database

        self.client_addr = client_writer.get_extra_info("peername")
        self.connection_id = f"{self.client_addr[0]}:{self.client_addr[1]}"
        self.ssl_negotiated = False

        # Client stream for decoding messages from client (no state machine for proxy phase)
        self.client_stream = PostgreSQLStream(
            client_reader,
            client_writer,
            codec.FrontendMessageDecoder(startup=True),
            state_machine=None,  # No state tracking needed during proxy phase
            connection_id=self.connection_id,
        )

        # Server connection (will be set during connection)
        self.server_reader: asyncio.StreamReader | None = None
        self.server_writer: asyncio.StreamWriter | None = None
        self.server_stream: PostgreSQLStream | None = None

        self.server_authenticated = False
        self.client_startup_params: dict[str, str] = {}
        self.server_parameters: list[messages.ParameterStatus] = []
        self.server_backend_key: messages.BackendKeyData | None = None

    async def handle(self):
        """Main proxy loop."""
        logger.info(f"[{self.connection_id}] New connection from {self.client_addr}")

        try:
            await self._connect_and_auth_to_server()
            if not self.server_authenticated:
                logger.error(f"[{self.connection_id}] Failed to authenticate to server")
                return

            await self._handle_client_trust_auth()

            client_to_server = asyncio.create_task(
                self._proxy_client_to_server(), name="client_to_server"
            )
            server_to_client = asyncio.create_task(
                self._proxy_server_to_client(), name="server_to_client"
            )

            done, pending = await asyncio.wait(
                [client_to_server, server_to_client],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            for task in done:
                if task.exception():
                    logger.error(
                        f"[{self.connection_id}] Task {task.get_name()} failed: {task.exception()}"
                    )

        except Exception as e:
            logger.error(f"[{self.connection_id}] Proxy error: {e}", exc_info=True)
        finally:
            await self._cleanup()

    async def _proxy_client_to_server(self):
        """Proxy messages from client to server (frontend messages)."""
        try:
            while True:
                data = await self.client_stream.reader.read(8192)
                if not data:
                    logger.info(f"[{self.connection_id}] Client disconnected")
                    break

                self.client_stream._decoder.feed(data)
                while True:
                    try:
                        msg = self.client_stream._read_buffered()
                        if msg is None:
                            break
                        await self._handle_frontend_message(msg)
                        # Forward message to server to update its state machines
                        if self.server_stream:
                            await self.server_stream.send_message(msg)
                    except Exception as e:
                        logger.error(f"[{self.connection_id}] Error decoding frontend message: {e}")
                        break

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[{self.connection_id}] Client->Server proxy error: {e}", exc_info=True)

    async def _proxy_server_to_client(self):
        """Proxy messages from server to client (backend messages).

        Decodes and logs messages for visibility, but no state machine validation.
        """
        try:
            assert self.server_stream is not None
            while True:
                data = await self.server_stream.reader.read(8192)
                if not data:
                    logger.info(f"[{self.connection_id}] Server disconnected")
                    break

                self.server_stream._decoder.feed(data)
                while True:
                    try:
                        msg = self.server_stream._read_buffered()
                        if msg is None:
                            break
                        await self._handle_backend_message(msg)
                        # Forward message to client (no state machine validation)
                        await self.client_stream.send_message(msg)
                    except Exception as e:
                        logger.error(f"[{self.connection_id}] Error decoding backend message: {e}")
                        break

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[{self.connection_id}] Server->Client proxy error: {e}", exc_info=True)

    async def _handle_frontend_message(
        self, msg: messages.PGMessage
    ) -> None:
        """Process a frontend message through the state machines."""
        msg_name = type(msg).__name__

        logger.info(f"[{self.connection_id}] → {msg_name} {self._format_message(msg)}")

    async def _handle_backend_message(self, msg: messages.PGMessage) -> None:
        """Process a backend message through the state machines."""
        msg_name = type(msg).__name__

        logger.info(f"[{self.connection_id}] ← {msg_name} {self._format_message(msg)}")

    def _format_message(self, msg) -> str:
        """Format message details for logging."""
        if isinstance(msg, messages.SSLRequest):
            return "(SSL negotiation request)"
        if isinstance(msg, messages.GSSEncRequest):
            return "(GSS encryption request)"
        if isinstance(msg, messages.CancelRequest):
            return f"(pid={msg.process_id}, key={msg.secret_key.hex()})"
        if isinstance(msg, messages.ErrorResponse):
            return f"(severity={msg.fields.get('S', '?')}, message={msg.fields.get('M', '?')})"
        if hasattr(msg, "query_string"):
            return f'(query="{msg.query_string[:50]}...")'
        if hasattr(msg, "query"):
            return f'(query="{msg.query[:50]}...")'
        if hasattr(msg, "tag"):
            return f"(tag={msg.tag})"
        if hasattr(msg, "status"):
            return f"(status={msg.status.name})"
        return ""

    async def _connect_to_server(self):
        """Establish connection to server, optionally with SSL."""
        self.server_reader, self.server_writer = await asyncio.open_connection(
            self.server_host, self.server_port
        )

        if self.server_ssl:
            await self._negotiate_ssl()

        logger.info(f"[{self.connection_id}] Connected to server")

    async def _negotiate_ssl(self):
        """Negotiate SSL/TLS with the server."""
        assert self.server_writer is not None
        assert self.server_reader is not None

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        # Send SSL request directly (no state tracking needed for this)
        ssl_req = messages.SSLRequest()
        self.server_writer.write(ssl_req.to_wire())
        await self.server_writer.drain()

        # Read SSL response (single byte, not a full message)
        response_byte = await self.server_reader.readexactly(1)
        ssl_response = messages.SSLResponse.from_bytes(response_byte)
        logger.info(f"[{self.connection_id}] Server SSL response: {ssl_response.name}")

        if ssl_response != messages.SSLResponse.SUPPORTED:
            raise RuntimeError("Server does not support SSL")

        await self.server_writer.start_tls(ssl_context, server_hostname=self.server_host)
        logger.info(f"[{self.connection_id}] SSL handshake complete")

    async def _authenticate_cleartext(self, stream: PostgreSQLStream):
        """Handle cleartext password authentication."""
        logger.info(f"[{self.connection_id}] Server requesting cleartext password")
        if not self.server_password:
            raise RuntimeError("No password provided for cleartext auth")

        pwd_msg = messages.PasswordMessage(password=self.server_password)
        await stream.send_message(pwd_msg)

    async def _authenticate_md5(
        self, msg: messages.AuthenticationMD5Password, stream: PostgreSQLStream
    ):
        """Handle MD5 password authentication."""
        logger.info(f"[{self.connection_id}] Server requesting MD5 password")
        if not self.server_password:
            raise RuntimeError("No password provided for MD5 auth")

        user = self.server_user or "postgres"
        md5_password = compute_md5_password(self.server_password, user, msg.salt)
        pwd_msg = messages.PasswordMessage(password=md5_password)
        await stream.send_message(pwd_msg)

    async def _authenticate_scram_start(
        self, msg: messages.AuthenticationSASL, stream: PostgreSQLStream
    ) -> dict[str, str]:
        """Start SCRAM-SHA-256 authentication."""
        logger.info(f"[{self.connection_id}] Server requesting SASL auth: {msg.mechanisms}")
        if "SCRAM-SHA-256" not in msg.mechanisms:
            raise RuntimeError("Only SCRAM-SHA-256 is supported")
        if not self.server_password:
            raise RuntimeError("No password provided for SCRAM")

        user = self.server_user or "postgres"
        client_first, client_first_bare, nonce = build_scram_client_first(user)

        sasl_msg = messages.SASLInitialResponse(
            mechanism="SCRAM-SHA-256", data=client_first.encode("utf-8")
        )
        await stream.send_message(sasl_msg)

        return {
            "username": user,
            "password": self.server_password,
            "client_nonce": nonce,
            "client_first_bare": client_first_bare,
        }

    async def _authenticate_scram_continue(
        self, msg: messages.AuthenticationSASLContinue, sasl_state: dict[str, str], stream: PostgreSQLStream
    ):
        """Continue SCRAM-SHA-256 authentication."""
        logger.info(f"[{self.connection_id}] SASL continue")

        server_first = msg.data.decode("utf-8")
        client_final = build_scram_client_final(
            server_first,
            sasl_state["client_nonce"],
            sasl_state["client_first_bare"],
            sasl_state["password"],
        )

        sasl_msg = messages.SASLResponse(data=client_final.encode("utf-8"))
        await stream.send_message(sasl_msg)

    async def _connect_and_auth_to_server(self):
        """Connect to server and authenticate.

        Uses a temporary state machine for validation during authentication phase only.
        """
        try:
            await self._connect_to_server()

            assert self.server_reader is not None
            assert self.server_writer is not None

            auth_stream = PostgreSQLStream(
                self.server_reader,
                self.server_writer,
                codec.BackendMessageDecoder(),
                state_machine=FrontendStateMachine(),
                connection_id=self.connection_id,
            )

            # Send startup message
            startup = messages.StartupMessage(
                params={
                    "user": self.server_user or "postgres",
                    "database": self.server_database or "postgres",
                }
            )
            await auth_stream.send_message(startup)
            logger.info(f"[{self.connection_id}] Sent startup to server")

            sasl_state: dict[str, str] | None = None

            while not self.server_authenticated:
                msg = await auth_stream.read_message()
                if msg is None:
                    logger.error(f"[{self.connection_id}] Server disconnected during auth")
                    return

                logger.info(f"[{self.connection_id}] Server auth: {type(msg).__name__}")

                if isinstance(msg, messages.AuthenticationCleartextPassword):
                    await self._authenticate_cleartext(auth_stream)

                elif isinstance(msg, messages.AuthenticationMD5Password):
                    await self._authenticate_md5(msg, auth_stream)

                elif isinstance(msg, messages.AuthenticationSASL):
                    sasl_state = await self._authenticate_scram_start(msg, auth_stream)

                elif isinstance(msg, messages.AuthenticationSASLContinue):
                    if sasl_state is None:
                        raise RuntimeError("No SASL state for continue")
                    await self._authenticate_scram_continue(msg, sasl_state, auth_stream)

                elif isinstance(msg, messages.AuthenticationSASLFinal):
                    logger.info(f"[{self.connection_id}] SCRAM-SHA-256 authentication complete")

                elif isinstance(msg, messages.AuthenticationOk):
                    logger.info(f"[{self.connection_id}] Server authenticated!")

                elif isinstance(msg, messages.ParameterStatus):
                    self.server_parameters.append(msg)

                elif isinstance(msg, messages.BackendKeyData):
                    self.server_backend_key = msg

                elif isinstance(msg, messages.ReadyForQuery):
                    self.server_authenticated = True
                    logger.info(f"[{self.connection_id}] Server authentication complete")
                    break

                elif isinstance(msg, messages.ErrorResponse):
                    severity = msg.fields.get("S", "?")
                    message = msg.fields.get("M", "?")
                    logger.error(
                        f"[{self.connection_id}] Server auth error: {severity} - {message}"
                    )
                    return

            # After authentication, create new stream without state machine for proxy phase
            self.server_stream = PostgreSQLStream(
                self.server_reader,
                self.server_writer,
                codec.BackendMessageDecoder(),
                state_machine=None,  # No state tracking during proxy phase
                connection_id=self.connection_id,
            )
            logger.info(f"[{self.connection_id}] Auth complete, switching to decoding-only mode")

        except Exception as e:
            logger.error(f"[{self.connection_id}] Error connecting to server: {e}", exc_info=True)

    async def _handle_client_trust_auth(self):
        """Handle client startup with trust authentication.

        Uses a local state machine for validation during authentication phase only.
        """
        try:
            auth_stream = PostgreSQLStream(
                self.client_stream.reader,
                self.client_stream.writer,
                self.client_stream._decoder,
                state_machine=BackendStateMachine(),
                connection_id=self.connection_id,
            )

            msg = await auth_stream.read_message()
            if msg is None:
                logger.error(f"[{self.connection_id}] Client disconnected before startup")
                return

            if isinstance(msg, messages.SSLRequest):
                logger.info(
                    f"[{self.connection_id}] Client requesting SSL (rejecting, not supported in auth proxy mode)"
                )
                await auth_stream.forward_raw(messages.SSLResponse.NOT_SUPPORTED.value)
                msg = await auth_stream.read_message()
                if msg is None:
                    logger.error(f"[{self.connection_id}] Client disconnected after SSL rejection")
                    return

            if not isinstance(msg, messages.StartupMessage):
                logger.error(
                    f"[{self.connection_id}] Expected StartupMessage, got {type(msg).__name__}"
                )
                return

            self.client_startup_params = msg.params
            logger.info(
                f"[{self.connection_id}] Client startup: user={msg.params.get('user')}, db={msg.params.get('database')}"
            )

            # Send authentication messages with state machine validation
            auth_ok = messages.AuthenticationOk()
            await auth_stream.send_message(auth_ok)

            for param in self.server_parameters:
                await auth_stream.send_message(param)

            if self.server_backend_key:
                await auth_stream.send_message(self.server_backend_key)

            ready = messages.ReadyForQuery(status=TransactionStatus.IDLE)
            await auth_stream.send_message(ready)

            logger.info(f"[{self.connection_id}] Client authenticated with trust auth")
            logger.info(f"[{self.connection_id}] Auth complete, switching to decoding-only mode")

        except Exception as e:
            logger.error(f"[{self.connection_id}] Error handling client auth: {e}", exc_info=True)

    async def _cleanup(self):
        """Clean up connections."""
        logger.info(f"[{self.connection_id}] Closing connection")

        if self.client_stream:
            try:
                self.client_stream.writer.close()
                await self.client_stream.writer.wait_closed()
            except Exception:
                pass

        if self.server_stream:
            try:
                self.server_stream.writer.close()
                await self.server_stream.writer.wait_closed()
            except Exception:
                pass


async def start_proxy(
    proxy_port: int,
    server_host: str,
    server_port: int,
    server_ssl: bool = False,
    server_user: str | None = None,
    server_password: str | None = None,
    server_database: str | None = None,
):
    """Start the proxy server."""

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        connection = ProxyConnection(
            reader,
            writer,
            server_host,
            server_port,
            server_ssl,
            server_user,
            server_password,
            server_database,
        )
        await connection.handle()

    server = await asyncio.start_server(handle_client, "0.0.0.0", proxy_port)

    addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
    logger.info(f"Proxy listening on {addrs}")
    logger.info(f"Forwarding to PostgreSQL at {server_host}:{server_port}")
    logger.info(f"Server: SSL={server_ssl}, User={server_user}, DB={server_database}")
    logger.info("Clients will use trust auth, proxy will authenticate to server")
    logger.info("Press Ctrl+C to stop")

    async with server:
        await server.serve_forever()


def main():
    proxy_port = int(os.getenv("PROXY_PORT", "5433"))
    server_host = os.getenv("PROXY_SERVER_HOST", "localhost")
    server_port = int(os.getenv("PROXY_SERVER_PORT", "5432"))

    server_ssl = os.getenv("PROXY_SERVER_SSL", "").lower() in ("true", "1", "yes")
    server_user = os.getenv("PROXY_SERVER_USER")
    server_password = os.getenv("PROXY_SERVER_PASSWORD")
    server_database = os.getenv("PROXY_SERVER_DATABASE")

    try:
        asyncio.run(
            start_proxy(
                proxy_port,
                server_host,
                server_port,
                server_ssl,
                server_user,
                server_password,
                server_database,
            )
        )
    except KeyboardInterrupt:
        logger.info("Proxy stopped by user")
        sys.exit(0)


def compute_md5_password(password: str, username: str, salt: bytes) -> str:
    """Compute PostgreSQL MD5 password hash."""
    import hashlib

    inner = hashlib.md5(f"{password}{username}".encode()).hexdigest()
    outer = hashlib.md5(f"{inner}".encode() + salt).hexdigest()
    return f"md5{outer}"


def build_scram_client_first(username: str) -> tuple[str, str, str]:
    """Build SCRAM-SHA-256 client-first-message."""
    import base64
    import secrets

    nonce = base64.b64encode(secrets.token_bytes(18)).decode("ascii")
    client_first_bare = f"n={username},r={nonce}"
    client_first = f"n,,{client_first_bare}"
    return client_first, client_first_bare, nonce


def build_scram_client_final(
    server_first: str, client_nonce: str, client_first_bare: str, password: str
) -> str:
    """Build SCRAM-SHA-256 client-final-message."""
    import base64
    import hashlib
    import hmac

    parts = dict(item.split("=", 1) for item in server_first.split(","))
    server_nonce = parts["r"]
    salt = base64.b64decode(parts["s"])
    iterations = int(parts["i"])

    if not server_nonce.startswith(client_nonce):
        raise RuntimeError("Invalid server nonce")

    channel_binding = base64.b64encode(b"n,,").decode("ascii")
    client_final_without_proof = f"c={channel_binding},r={server_nonce}"

    password_bytes = password.encode("utf-8")
    salted_password = hashlib.pbkdf2_hmac("sha256", password_bytes, salt, iterations)
    client_key = hmac.new(salted_password, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    auth_message = f"{client_first_bare},{server_first},{client_final_without_proof}"
    client_signature = hmac.new(stored_key, auth_message.encode("utf-8"), hashlib.sha256).digest()
    client_proof = bytes(a ^ b for a, b in zip(client_key, client_signature, strict=True))
    client_proof_b64 = base64.b64encode(client_proof).decode("ascii")

    return f"{client_final_without_proof},p={client_proof_b64}"


if __name__ == "__main__":
    main()
