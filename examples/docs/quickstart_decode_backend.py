"""Quickstart: Decoding server messages (client-side)."""

from pygwire import BackendMessageDecoder
from pygwire.messages import AuthenticationOk

decoder = BackendMessageDecoder()

# Feed raw bytes received from the server
decoder.feed(AuthenticationOk().to_wire())

# Iterate over decoded messages
for msg in decoder:
    print(f"Decoded: {type(msg).__name__}")  # "Decoded: AuthenticationOk"
