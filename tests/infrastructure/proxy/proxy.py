#!/usr/bin/env python3
"""Transparent PostgreSQL protocol proxy for testing codec and state machine.

This proxy sits between a PostgreSQL client (e.g., psql) and server, decoding
and validating all messages using the pygwire Connection classes.

Usage:
    python proxy.py [--proxy-port 5433] [--server-host localhost] [--server-port 5432]

Then connect with psql:
    psql -h localhost -p 5433 -U youruser yourdb
"""

import argparse
import asyncio
import logging
import sys

from pygwire.connection import BackendConnection, FrontendConnection
from pygwire.messages import PGMessage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class ProxyConnection:
    """Handles a single proxied PostgreSQL connection.

    Models the proxy as two real connections:
    - client_conn (BackendConnection): proxy acts as server to the client
    - server_conn (FrontendConnection): proxy acts as client to the server

    Messages flow: client → client_conn.receive() → server_conn.send() → server
    And back:      server → server_conn.receive() → client_conn.send() → client

    Both state machines stay in sync naturally because every message passes
    through both connections.
    """

    def __init__(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        server_host: str,
        server_port: int,
        strict: bool = False,
    ):
        self.client_reader = client_reader
        self.client_writer = client_writer
        self.server_host = server_host
        self.server_port = server_port

        self.server_reader: asyncio.StreamReader | None = None
        self.server_writer: asyncio.StreamWriter | None = None

        # Proxy as server to client, client to server
        self.client_conn = BackendConnection(strict=strict)
        self.server_conn = FrontendConnection(strict=strict)

        # Track connection state
        self.client_addr = client_writer.get_extra_info("peername")
        self.connection_id = f"{self.client_addr[0]}:{self.client_addr[1]}"

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
        """Proxy: client → client_conn.receive() → server_conn.send() → server."""
        while True:
            data = await self.client_reader.read(8192)
            if not data:
                logger.info(f"[{self.connection_id}] Client disconnected")
                break

            for msg in self.client_conn.receive(data):
                wire = self.server_conn.send(msg)
                if self.server_writer:
                    self.server_writer.write(wire)
                self._log_message("→", msg)
            if self.server_writer:
                await self.server_writer.drain()

    async def _proxy_server_to_client(self):
        """Proxy: server → server_conn.receive() → client_conn.send() → client."""
        while True:
            data = await self.server_reader.read(8192)
            if not data:
                logger.info(f"[{self.connection_id}] Server disconnected")
                break

            for msg in self.server_conn.receive(data):
                wire = self.client_conn.send(msg)
                self.client_writer.write(wire)
                self._log_message("←", msg)
            await self.client_writer.drain()

    def _log_message(self, direction: str, msg: PGMessage) -> None:
        """Log a message with direction arrow."""
        msg_name = type(msg).__name__
        logger.info(f"[{self.connection_id}] {direction} {msg_name} {msg}")
        logger.debug(
            f"[{self.connection_id}]   Client phase: {self.client_conn.phase.name}, "
            f"Server phase: {self.server_conn.phase.name}"
        )

    async def _cleanup(self):
        """Clean up connections."""
        logger.info(
            f"[{self.connection_id}] Closing connection "
            f"(Client={self.client_conn.phase.name}, "
            f"Server={self.server_conn.phase.name})"
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


async def start_proxy(proxy_port: int, server_host: str, server_port: int, strict: bool = False):
    """Start the proxy server."""

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        connection = ProxyConnection(reader, writer, server_host, server_port, strict)
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
