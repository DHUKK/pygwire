"""Framing: selecting strategies with lookup_framing."""

from pygwire.constants import ConnectionPhase, MessageDirection
from pygwire.framing import NegotiationFraming, StandardFraming, StartupFraming, lookup_framing

startup = lookup_framing(ConnectionPhase.STARTUP, MessageDirection.FRONTEND)
print(type(startup).__name__)  # StartupFraming
assert isinstance(startup, StartupFraming)

negotiation = lookup_framing(ConnectionPhase.SSL_NEGOTIATION, MessageDirection.BACKEND)
print(type(negotiation).__name__)  # NegotiationFraming
assert isinstance(negotiation, NegotiationFraming)

standard = lookup_framing(ConnectionPhase.READY, MessageDirection.FRONTEND)
print(type(standard).__name__)  # StandardFraming
assert isinstance(standard, StandardFraming)
