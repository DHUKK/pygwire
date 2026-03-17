"""Message registry system for PostgreSQL wire protocol.

This module provides the registry infrastructure that maps message identifiers
and request codes to message classes. It supports three types of registries
for different framing modes:

- StandardMessageRegistry: Standard framed messages (Byte1 + Int32 + payload)
- StartupMessageRegistry: Startup messages (Int32 + payload, request code discriminator)
- NegotiationMessageRegistry: SSL/GSS negotiation (single byte messages)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pygwire.constants import ConnectionPhase, MessageDirection
    from pygwire.messages._base import PGMessage


class StandardMessageRegistry:
    """Registry for standard framed messages (Byte1 + Int32 + payload).

    Standard messages have a 1-byte identifier followed by a 4-byte length
    and payload. The same identifier can map to different message classes
    depending on the connection phase and direction.

    Example:
        - Identifier b"p" in AUTHENTICATING phase → PasswordMessage
        - Identifier b"p" in AUTHENTICATING_SASL_INITIAL phase → SASLInitialResponse
    """

    def __init__(self) -> None:
        # Key: (identifier, phase, direction) → message class
        # phase=None means valid in all phases
        self._registry: dict[
            tuple[bytes, ConnectionPhase | None, MessageDirection], type[PGMessage]
        ] = {}

    def register(
        self,
        identifier: bytes,
        direction: MessageDirection,
        phases: frozenset[ConnectionPhase] | None = None,
    ) -> Callable[[type[PGMessage]], type[PGMessage]]:
        """Decorator to register a standard message class.

        Args:
            identifier: Single-byte message identifier (e.g., b"Q" for Query)
            direction: Who sends this message (FRONTEND or BACKEND)
            phases: Connection phases where this message is valid.
                    None or empty frozenset means valid in all phases.

        Example::

            @STANDARD_REGISTRY.register(
                b"Q",
                direction=MessageDirection.FRONTEND,
                phases=frozenset({ConnectionPhase.READY}),
            )
            class Query(FrontendMessage):
                ...
        """

        def decorator(cls: type[PGMessage]) -> type[PGMessage]:
            # Set the identifier on the class if not already set
            if not cls.identifier:
                cls.identifier = identifier

            if phases:
                # Register for each specific phase
                for phase in phases:
                    self._registry[(identifier, phase, direction)] = cls
            else:
                # None = valid in all phases
                self._registry[(identifier, None, direction)] = cls
            return cls

        return decorator

    def lookup(
        self,
        identifier: bytes,
        phase: ConnectionPhase,
        direction: MessageDirection,
    ) -> type[PGMessage] | None:
        """Find message class matching identifier, phase, and direction.

        Args:
            identifier: Single-byte message identifier
            phase: Current connection phase
            direction: Message direction (FRONTEND or BACKEND)

        Returns:
            Message class or None if not found

        Lookup strategy:
            1. Try exact (identifier, phase, direction) match
            2. Fall back to (identifier, None, direction) wildcard phase match
        """
        # Try exact phase match first
        if (identifier, phase, direction) in self._registry:
            return self._registry[(identifier, phase, direction)]
        # Fall back to wildcard phase
        return self._registry.get((identifier, None, direction))


class StartupMessageRegistry:
    """Registry for startup messages (Int32 + payload, request code discriminator).

    Startup messages have no identifier byte. Instead, they use a 4-byte request
    code at the start of the payload to distinguish message types:
        - 0x00030000: StartupMessage
        - 80877103: SSLRequest
        - 80877104: GSSEncRequest
        - 80877102: CancelRequest

    All startup messages are FRONTEND (sent by client).
    """

    def __init__(self) -> None:
        # Key: request_code → message class
        self._registry: dict[int, type[PGMessage]] = {}

    def register(self, request_code: int) -> Callable[[type[PGMessage]], type[PGMessage]]:
        """Decorator to register a startup message class.

        Args:
            request_code: 32-bit version/request code

        Example::

            @STARTUP_REGISTRY.register(request_code=0x00030000)
            class StartupMessage(SpecialMessage):
                ...
        """

        def decorator(cls: type[PGMessage]) -> type[PGMessage]:
            self._registry[request_code] = cls
            return cls

        return decorator

    def lookup(self, request_code: int) -> type[PGMessage] | None:
        """Find message class by request code.

        Args:
            request_code: 32-bit version/request code

        Returns:
            Message class or None if not found
        """
        return self._registry.get(request_code)


class NegotiationMessageRegistry:
    """Registry for SSL/GSS negotiation messages (single byte).

    Negotiation messages are single bytes with no length field:
        - b"S": SSL accepted
        - b"N": SSL/GSS rejected
        - b"G": GSS accepted

    All negotiation messages are BACKEND (sent by server).
    """

    def __init__(self) -> None:
        # Key: (byte_value, phase) → message class
        self._registry: dict[tuple[bytes, ConnectionPhase], type[PGMessage]] = {}

    def register(
        self, byte_value: bytes, phase: ConnectionPhase
    ) -> Callable[[type[PGMessage]], type[PGMessage]]:
        """Decorator to register a negotiation message class.

        Args:
            byte_value: Single byte value (e.g., b"S" for SSL accepted)
            phase: Connection phase (SSL_NEGOTIATION or GSS_NEGOTIATION)

        Example::

            @NEGOTIATION_REGISTRY.register(b"S", ConnectionPhase.SSL_NEGOTIATION)
            @NEGOTIATION_REGISTRY.register(b"N", ConnectionPhase.SSL_NEGOTIATION)
            class SSLResponse(BackendMessage):
                ...
        """

        def decorator(cls: type[PGMessage]) -> type[PGMessage]:
            self._registry[(byte_value, phase)] = cls
            return cls

        return decorator

    def lookup(self, byte_value: bytes, phase: ConnectionPhase) -> type[PGMessage] | None:
        """Find message class by byte value and phase.

        Args:
            byte_value: Single byte value
            phase: Connection phase

        Returns:
            Message class or None if not found
        """
        return self._registry.get((byte_value, phase))


# Global registry instances
STANDARD_REGISTRY = StandardMessageRegistry()
STARTUP_REGISTRY = StartupMessageRegistry()
NEGOTIATION_REGISTRY = NegotiationMessageRegistry()
