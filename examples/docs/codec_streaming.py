"""Codec: Streaming and partial messages."""

from pygwire.codec import FrontendMessageDecoder
from pygwire.messages import StartupMessage

decoder = FrontendMessageDecoder()

# Create a startup message and convert to wire format
startup_msg = StartupMessage(params={"user": "postgres", "database": "postgres"})
wire_data = startup_msg.to_wire()

# Split the wire data into three chunks to simulate streaming
chunk_size = len(wire_data) // 3
first_chunk = wire_data[:chunk_size]
second_chunk = wire_data[chunk_size : chunk_size * 2]
third_chunk = wire_data[chunk_size * 2 :]

# Feed chunks one at a time - decoder buffers until complete message
decoder.feed(first_chunk)
decoder.feed(second_chunk)
decoder.feed(third_chunk)

# Now the complete message is available
msg = None
for m in decoder:
    msg = m
    break

print(f"Decoded: {type(msg).__name__}")
print(f"User: {msg}")
