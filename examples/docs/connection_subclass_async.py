"""Connection: Subclassing for I/O - asynchronous."""

import asyncio
from collections.abc import AsyncIterator

from pygwire.connection import FrontendConnection
from pygwire.messages import PGMessage


class AsyncConnection(FrontendConnection):
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        super().__init__()
        self._reader = reader
        self._writer = writer

    def on_send(self, data: bytes) -> None:
        self._writer.write(data)

    async def send_message(self, msg: PGMessage) -> None:
        self.send(msg)
        await self._writer.drain()

    async def recv_messages(self) -> AsyncIterator[PGMessage]:
        data = await self._reader.read(8192)
        if not data:
            return
        for msg in self.receive(data):
            yield msg
