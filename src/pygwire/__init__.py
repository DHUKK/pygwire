"""Pygwire: Low-level PostgreSQL wire protocol codec for Python."""

from importlib.metadata import version

from pygwire.connection import (
    BackendConnection,
    Connection,
    FrontendConnection,
)
from pygwire.constants import ConnectionPhase, ProtocolVersion, TransactionStatus
from pygwire.state_machine import (
    BackendStateMachine,
    FrontendStateMachine,
    StateMachineError,
)

__version__ = version("pygwire")

__all__ = [
    "Connection",
    "FrontendConnection",
    "BackendConnection",
    "ProtocolVersion",
    "TransactionStatus",
    "BackendStateMachine",
    "ConnectionPhase",
    "FrontendStateMachine",
    "StateMachineError",
]
