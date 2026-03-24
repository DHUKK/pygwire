"""Codec: Basic usage."""

from pygwire import ConnectionPhase, FrontendMessageDecoder
from pygwire.messages import Query, StartupMessage

decoder = FrontendMessageDecoder()
# Decoder starts in STARTUP phase

startup_msg = StartupMessage(params={"user": "postgres", "database": "postgres"})
decoder.feed(startup_msg.to_wire())

# Read messages one at a time
msg = next(decoder)
print(msg)  # StartupMessage(params={'user': 'postgres', 'database': 'postgres'}, ...)

# After startup, transition to READY phase for standard (query) messages
decoder.phase = ConnectionPhase.READY
# (Connection class handles this automatically)

query_msg = Query(query_string="SELECT 1")
decoder.feed(query_msg.to_wire())

# Or iterate over all available messages
for msg in decoder:
    print(msg)  # Query(query_string='SELECT 1')
