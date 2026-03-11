"""Pygwire exception hierarchy."""

__all__ = [
    "DecodingError",
    "FramingError",
    "ProtocolError",
    "PygwireError",
    "StateMachineError",
]


class PygwireError(Exception):
    """Base exception for all Pygwire errors."""


class ProtocolError(PygwireError):
    """Raised when protocol framing or content is invalid."""


class FramingError(ProtocolError):
    """Raised when message framing is invalid (size, identifier, truncation)."""


class DecodingError(ProtocolError):
    """Raised when a message payload cannot be decoded."""


class StateMachineError(ProtocolError):
    """Raised when an invalid message is sent/received for the current state."""
