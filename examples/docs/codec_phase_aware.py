"""Codec: Phase-aware framing."""

from pygwire import ConnectionPhase, FrontendMessageDecoder
from pygwire.messages import StartupMessage

decoder = FrontendMessageDecoder()
assert decoder.phase == ConnectionPhase.STARTUP  # Start in STARTUP

# Simulate client data (would come from socket.recv())
first_data_from_client = StartupMessage(params={"user": "postgres", "database": "mydb"}).to_wire()

decoder.feed(first_data_from_client)

for msg in decoder:
    # First message will be StartupMessage, SSLRequest, etc.
    print(msg)

    # Manually update phase based on message
    if isinstance(msg, StartupMessage):
        decoder.phase = ConnectionPhase.AUTHENTICATING
        print(decoder.phase)
