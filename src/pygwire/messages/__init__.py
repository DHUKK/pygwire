"""PostgreSQL wire protocol messages.

This module provides message classes for the PostgreSQL wire protocol.
All messages are organized internally by protocol phase but exposed here
in a flat namespace for convenient importing.
"""

# Authentication
from ._auth import (
    Authentication,
    AuthenticationCleartextPassword,
    AuthenticationGSS,
    AuthenticationGSSContinue,
    AuthenticationKerberosV5,
    AuthenticationMD5Password,
    AuthenticationOk,
    AuthenticationSASL,
    AuthenticationSASLContinue,
    AuthenticationSASLFinal,
    AuthenticationSSPI,
    GSSResponse,
    PasswordMessage,
    SASLInitialResponse,
    SASLResponse,
    SSLResponse,
)
from ._base import (
    BackendMessage,
    CommonMessage,
    FrontendMessage,
    PGMessage,
    ProtocolError,
    PygwireError,
    SpecialMessage,
)

# COPY protocol
from ._copy import (
    CopyData,
    CopyDone,
    CopyFail,
    CopyInResponse,
    CopyOutResponse,
)

# Errors
from ._error import (
    ErrorResponse,
)

# Extended query protocol
from ._extended_query import (
    Bind,
    BindComplete,
    Close,
    CloseComplete,
    Describe,
    Execute,
    Flush,
    NoData,
    ParameterDescription,
    Parse,
    ParseComplete,
    PortalSuspended,
    Sync,
)

# Miscellaneous
from ._misc import (
    BackendKeyData,
    FunctionCall,
    FunctionCallResponse,
    NegotiateProtocolVersion,
    Terminate,
)

# Notifications and status
from ._notification import (
    NoticeResponse,
    NotificationResponse,
    ParameterStatus,
)
from ._registry import (
    NEGOTIATION_REGISTRY,
    STANDARD_REGISTRY,
    STARTUP_REGISTRY,
)

# Simple query protocol
from ._simple_query import (
    CommandComplete,
    DataRow,
    EmptyQueryResponse,
    FieldDescription,
    Query,
    ReadyForQuery,
    RowDescription,
)

# Startup phase
from ._startup import (
    CancelRequest,
    GSSEncRequest,
    SSLRequest,
    StartupMessage,
)

__all__ = [
    # Registries
    "STANDARD_REGISTRY",
    "STARTUP_REGISTRY",
    "NEGOTIATION_REGISTRY",
    # Base classes and exceptions
    "PGMessage",
    "FrontendMessage",
    "BackendMessage",
    "CommonMessage",
    "SpecialMessage",
    "ProtocolError",
    "PygwireError",
    # Startup phase
    "StartupMessage",
    "SSLRequest",
    "GSSEncRequest",
    "CancelRequest",
    # Authentication
    "SSLResponse",
    "GSSResponse",
    "Authentication",
    "AuthenticationOk",
    "AuthenticationKerberosV5",
    "AuthenticationCleartextPassword",
    "AuthenticationMD5Password",
    "AuthenticationGSS",
    "AuthenticationGSSContinue",
    "AuthenticationSSPI",
    "AuthenticationSASL",
    "AuthenticationSASLContinue",
    "AuthenticationSASLFinal",
    "PasswordMessage",
    "SASLInitialResponse",
    "SASLResponse",
    # Simple query protocol
    "Query",
    "RowDescription",
    "FieldDescription",
    "DataRow",
    "CommandComplete",
    "ReadyForQuery",
    "EmptyQueryResponse",
    # Extended query protocol
    "Parse",
    "ParseComplete",
    "Bind",
    "BindComplete",
    "Describe",
    "Execute",
    "Close",
    "CloseComplete",
    "Sync",
    "Flush",
    "ParameterDescription",
    "NoData",
    "PortalSuspended",
    # COPY protocol
    "CopyData",
    "CopyDone",
    "CopyFail",
    "CopyInResponse",
    "CopyOutResponse",
    # Notifications and status
    "NotificationResponse",
    "NoticeResponse",
    "ParameterStatus",
    # Errors
    "ErrorResponse",
    # Miscellaneous
    "BackendKeyData",
    "FunctionCall",
    "FunctionCallResponse",
    "Terminate",
    "NegotiateProtocolVersion",
]
