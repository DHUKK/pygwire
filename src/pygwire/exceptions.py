"""Pygwire exception hierarchy."""


class PygwireError(Exception):
    """Base exception for all Pygwire errors."""


class ProtocolError(PygwireError):
    """Raised when protocol framing or content is invalid."""
