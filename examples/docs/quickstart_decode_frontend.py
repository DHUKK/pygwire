"""Quickstart: Decoding client messages (server/proxy-side)."""

from pygwire.codec import FrontendMessageDecoder
from pygwire.constants import ConnectionPhase
from pygwire.messages import Query, StartupMessage

decoder = FrontendMessageDecoder()

# Simulate a client sending a startup message
startup = StartupMessage(params={"user": "postgres", "database": "mydb"})
decoder.feed(startup.to_wire())

for msg in decoder:
    if isinstance(msg, StartupMessage):
        print(f"Client connecting: user={msg.params.get('user')}")
        # Transition to authentication phase
        decoder.phase = ConnectionPhase.AUTHENTICATING

# After authentication completes, transition to READY
decoder.phase = ConnectionPhase.READY

# Now decode standard messages
query = Query(query_string="SELECT 1")
decoder.feed(query.to_wire())

for msg in decoder:
    if isinstance(msg, Query):
        print(f"Query: {msg.query_string}")
