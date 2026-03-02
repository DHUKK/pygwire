#!/usr/bin/env python3
"""Transparent PostgreSQL protocol proxy for testing codec and state machine.

This proxy sits between a PostgreSQL client (e.g., psql) and server, decoding
and validating all messages using the pygwire codec and state machine.

Usage:
    python proxy.py [--proxy-port 5433] [--server-host localhost] [--server-port 5432]

Then connect with psql:
    psql -h localhost -p 5433 -U youruser yourdb
"""

import argparse
import asyncio
import logging
import sys

from pygwire.codec import BackendMessageDecoder, FrontendMessageDecoder
from pygwire.messages import (
    BackendMessage,
    CancelRequest,
    ErrorResponse,
    FrontendMessage,
    GSSEncRequest,
    SpecialMessage,
    SSLRequest,
    SSLResponse,
)
from pygwire.state_machine import (
    BackendStateMachine,
    ConnectionPhase,
    FrontendStateMachine,
    StateMachineError,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class ProxyConnection:
    """Handles a single client connection, proxying to the PostgreSQL server."""

    def __init__(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        server_host: str,
        server_port: int,
        strict_mode: bool = False,
    ):
        self.client_reader = client_reader
        self.client_writer = client_writer
        self.server_host = server_host
        self.server_port = server_port
        self.strict_mode = strict_mode

        self.server_reader: asyncio.StreamReader | None = None
        self.server_writer: asyncio.StreamWriter | None = None

        # Decoders for each direction
        self.frontend_decoder = FrontendMessageDecoder(startup=True)  # Decodes frontend messages
        self.backend_decoder = BackendMessageDecoder()  # Decodes backend messages

        # State machines for each side
        self.frontend_sm = FrontendStateMachine()
        self.backend_sm = BackendStateMachine()

        # Track connection state
        self.client_addr = client_writer.get_extra_info("peername")
        self.connection_id = f"{self.client_addr[0]}:{self.client_addr[1]}"
        self.ssl_negotiated = False

    async def handle(self):
        """Main proxy loop."""
        logger.info(f"[{self.connection_id}] New connection from {self.client_addr}")

        try:
            # Connect to PostgreSQL server
            self.server_reader, self.server_writer = await asyncio.open_connection(
                self.server_host, self.server_port
            )
            logger.info(
                f"[{self.connection_id}] Connected to server {self.server_host}:{self.server_port}"
            )

            # Create tasks for bidirectional proxying
            client_to_server = asyncio.create_task(
                self._proxy_client_to_server(), name="client_to_server"
            )
            server_to_client = asyncio.create_task(
                self._proxy_server_to_client(), name="server_to_client"
            )

            # Wait for either direction to complete
            done, pending = await asyncio.wait(
                [client_to_server, server_to_client],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel the other task
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Check for exceptions
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
                # Read data from client
                data = await self.client_reader.read(8192)
                if not data:
                    logger.info(f"[{self.connection_id}] Client disconnected")
                    break

                # Feed to decoder
                self.frontend_decoder.feed(data)

                # Process all available messages
                while True:
                    try:
                        msg = self.frontend_decoder.read()
                        if msg is None:
                            break

                        await self._handle_frontend_message(msg)

                    except Exception as e:
                        logger.error(f"[{self.connection_id}] Error decoding frontend message: {e}")
                        break

                # Forward raw data to server
                if self.server_writer:
                    self.server_writer.write(data)
                    await self.server_writer.drain()

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[{self.connection_id}] Client->Server proxy error: {e}", exc_info=True)

    async def _proxy_server_to_client(self):
        """Proxy messages from server to client (backend messages)."""
        try:
            while True:
                # Read data from server
                data = await self.server_reader.read(8192)
                if not data:
                    logger.info(f"[{self.connection_id}] Server disconnected")
                    break

                # Check for SSL/GSS negotiation response (single byte)
                if self.frontend_sm.phase == ConnectionPhase.SSL_NEGOTIATION and len(data) == 1:
                    response = SSLResponse.from_bytes(data)
                    logger.info(f"[{self.connection_id}] ← SSL Response: {response.name}")
                    # Don't feed to decoder - it's not a message
                    self.client_writer.write(data)
                    await self.client_writer.drain()
                    continue

                if self.frontend_sm.phase == ConnectionPhase.GSS_NEGOTIATION and len(data) == 1:
                    logger.info(f"[{self.connection_id}] ← GSS Response: {data[0]:02x}")
                    self.client_writer.write(data)
                    await self.client_writer.drain()
                    continue

                # Feed to decoder
                self.backend_decoder.feed(data)

                # Process all available messages
                while True:
                    try:
                        msg = self.backend_decoder.read()
                        if msg is None:
                            break

                        await self._handle_backend_message(msg)

                    except Exception as e:
                        logger.error(f"[{self.connection_id}] Error decoding backend message: {e}")
                        break

                # Forward raw data to client
                self.client_writer.write(data)
                await self.client_writer.drain()

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[{self.connection_id}] Server->Client proxy error: {e}", exc_info=True)

    async def _handle_frontend_message(self, msg: FrontendMessage | SpecialMessage) -> None:
        """Process a frontend message through the state machines."""
        msg_name = type(msg).__name__

        # Log the message
        logger.info(f"[{self.connection_id}] → {msg_name} {self._format_message(msg)}")

        # Validate with frontend state machine (client perspective)
        try:
            self.frontend_sm.send(msg)
            logger.debug(
                f"[{self.connection_id}]   Frontend phase: {self.frontend_sm.phase.name}, "
                f"pending_syncs: {self.frontend_sm.pending_syncs}"
            )
        except StateMachineError as e:
            if self.strict_mode:
                logger.error(f"[{self.connection_id}] Frontend SM error: {e}")
                sys.exit(1)
            logger.warning(f"[{self.connection_id}]   ⚠️  Frontend SM: {e}")

        # Validate with backend state machine (server perspective)
        try:
            self.backend_sm.receive(msg)
            logger.debug(
                f"[{self.connection_id}]   Backend phase: {self.backend_sm.phase.name}, "
                f"pending_syncs: {self.backend_sm.pending_syncs}"
            )
        except StateMachineError as e:
            if self.strict_mode:
                logger.error(f"[{self.connection_id}] Backend SM error: {e}")
                sys.exit(1)
            logger.warning(f"[{self.connection_id}]   ⚠️  Backend SM: {e}")

        # Check phase consistency
        if self.frontend_sm.phase != self.backend_sm.phase:
            logger.debug(
                f"[{self.connection_id}]   ⚠️  Phase mismatch: "
                f"Frontend={self.frontend_sm.phase.name}, "
                f"Backend={self.backend_sm.phase.name}"
            )

    async def _handle_backend_message(self, msg: BackendMessage) -> None:
        """Process a backend message through the state machines."""
        msg_name = type(msg).__name__

        # Log the message
        logger.info(f"[{self.connection_id}] ← {msg_name} {self._format_message(msg)}")

        # Validate with backend state machine (server perspective)
        try:
            self.backend_sm.send(msg)
            logger.debug(
                f"[{self.connection_id}]   Backend phase: {self.backend_sm.phase.name}, "
                f"pending_syncs: {self.backend_sm.pending_syncs}"
            )
        except StateMachineError as e:
            if self.strict_mode:
                logger.error(f"[{self.connection_id}] Backend SM error: {e}")
                sys.exit(1)
            logger.warning(f"[{self.connection_id}]   ⚠️  Backend SM: {e}")

        # Validate with frontend state machine (client perspective)
        try:
            self.frontend_sm.receive(msg)
            logger.debug(
                f"[{self.connection_id}]   Frontend phase: {self.frontend_sm.phase.name}, "
                f"pending_syncs: {self.frontend_sm.pending_syncs}"
            )
        except StateMachineError as e:
            if self.strict_mode:
                logger.error(f"[{self.connection_id}] Frontend SM error: {e}")
                sys.exit(1)
            logger.warning(f"[{self.connection_id}]   ⚠️  Frontend SM: {e}")

        # Check phase consistency
        if self.frontend_sm.phase != self.backend_sm.phase:
            logger.debug(
                f"[{self.connection_id}]   ⚠️  Phase mismatch: "
                f"Frontend={self.frontend_sm.phase.name}, "
                f"Backend={self.backend_sm.phase.name}"
            )

    def _format_message(self, msg) -> str:
        """Format message details for logging."""
        if isinstance(msg, SSLRequest):
            return "(SSL negotiation request)"
        elif isinstance(msg, GSSEncRequest):
            return "(GSS encryption request)"
        elif isinstance(msg, CancelRequest):
            return f"(pid={msg.process_id}, key={msg.secret_key.hex()})"
        elif isinstance(msg, ErrorResponse):
            severity = msg.fields.get("S", "?")
            message = msg.fields.get("M", "?")
            return f"(severity={severity}, message={message})"
        elif hasattr(msg, "query_string"):
            query = msg.query_string[:50]
            return f'(query="{query}...")'
        elif hasattr(msg, "query"):
            query = msg.query[:50]
            return f'(query="{query}...")'
        elif hasattr(msg, "tag"):
            return f"(tag={msg.tag})"
        elif hasattr(msg, "status"):
            return f"(status={msg.status.name})"
        return ""

    async def _cleanup(self):
        """Clean up connections."""
        logger.info(
            f"[{self.connection_id}] Closing connection "
            f"(Frontend={self.frontend_sm.phase.name}, "
            f"Backend={self.backend_sm.phase.name})"
        )

        if self.client_writer:
            try:
                self.client_writer.close()
                await self.client_writer.wait_closed()
            except Exception:
                pass

        if self.server_writer:
            try:
                self.server_writer.close()
                await self.server_writer.wait_closed()
            except Exception:
                pass


async def start_proxy(
    proxy_port: int, server_host: str, server_port: int, strict_mode: bool = False
):
    """Start the proxy server."""

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        connection = ProxyConnection(reader, writer, server_host, server_port, strict_mode)
        await connection.handle()

    server = await asyncio.start_server(handle_client, "0.0.0.0", proxy_port)

    addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
    logger.info(f"Proxy listening on {addrs}")
    logger.info(f"Forwarding to PostgreSQL at {server_host}:{server_port}")
    logger.info("Press Ctrl+C to stop")

    async with server:
        await server.serve_forever()


def main():
    parser = argparse.ArgumentParser(
        description="Transparent PostgreSQL protocol proxy for testing"
    )
    parser.add_argument(
        "--proxy-port", type=int, default=5433, help="Port to listen on (default: 5433)"
    )
    parser.add_argument(
        "--server-host",
        type=str,
        default="localhost",
        help="PostgreSQL server host (default: localhost)",
    )
    parser.add_argument(
        "--server-port",
        type=int,
        default=5432,
        help="PostgreSQL server port (default: 5432)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with error code on state machine errors (for testing)",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        asyncio.run(start_proxy(args.proxy_port, args.server_host, args.server_port, args.strict))
    except KeyboardInterrupt:
        logger.info("Proxy stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
