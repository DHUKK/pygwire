"""Pygwire: Low-level PostgreSQL wire protocol codec for Python."""

from importlib.metadata import version

from .codec import (
    BackendMessageDecoder,
    FrontendMessageDecoder,
)
from .constants import ProtocolVersion, TransactionStatus
from .state_machine import (
    BackendStateMachine,
    ConnectionPhase,
    FrontendStateMachine,
    StateMachineError,
)

__version__ = version("pygwire")

__all__ = [
    "FrontendMessageDecoder",
    "BackendMessageDecoder",
    "ProtocolVersion",
    "TransactionStatus",
    "BackendStateMachine",
    "ConnectionPhase",
    "FrontendStateMachine",
    "StateMachineError",
]
