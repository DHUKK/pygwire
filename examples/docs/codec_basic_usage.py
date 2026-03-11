"""Codec: Basic usage."""

from pygwire import FrontendMessageDecoder
from pygwire.messages import StartupMessage

decoder = FrontendMessageDecoder()

# Feed bytes from your transport layer
# (Using fake data for demonstration)
startup_msg = StartupMessage(params={"user": "postgres", "database": "postgres"})
raw_bytes = startup_msg.to_wire()
decoder.feed(raw_bytes)

# Read messages one at a time
msg = next(decoder)
print(msg)

# Or iterate over all available messages
for msg in decoder:
    print(msg)
    # Update phase as connection progresses
    # (Connection class handles this automatically)
