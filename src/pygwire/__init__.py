"""Pygwire: Low-level PostgreSQL wire protocol codec for Python."""

from importlib.metadata import version

from pygwire.codec import BackendMessageDecoder, FrontendMessageDecoder
from pygwire.connection import (
    BackendConnection,
    Connection,
    FrontendConnection,
)
from pygwire.constants import ConnectionPhase, StartupRequestCode, TransactionStatus
from pygwire.exceptions import (
    DecodingError,
    FramingError,
    ProtocolError,
    PygwireError,
    StateMachineError,
)
from pygwire.state_machine import (
    BackendStateMachine,
    FrontendStateMachine,
)

__version__ = version("pygwire")

__all__ = [
    "BackendConnection",
    "BackendMessageDecoder",
    "BackendStateMachine",
    "Connection",
    "ConnectionPhase",
    "DecodingError",
    "FramingError",
    "FrontendConnection",
    "FrontendMessageDecoder",
    "FrontendStateMachine",
    "ProtocolError",
    "StartupRequestCode",
    "PygwireError",
    "StateMachineError",
    "TransactionStatus",
]
