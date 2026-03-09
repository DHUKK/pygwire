from enum import Enum, IntEnum, StrEnum, auto


class MessageDirection(StrEnum):
    """Message direction: indicates who sends this message type.

    - FRONTEND: Message sent by client (frontend → backend)
    - BACKEND: Message sent by server (backend → frontend)

    Examples:
        - Query is FRONTEND (client sends queries to server)
        - RowDescription is BACKEND (server sends row descriptions to client)
        - StartupMessage is FRONTEND (client initiates connection)
        - ReadyForQuery is BACKEND (server signals ready state)
    """

    FRONTEND = "frontend"
    BACKEND = "backend"


class ConnectionPhase(Enum):
    """Connection phases in the PostgreSQL wire protocol lifecycle.

    The protocol follows this general flow:

    Frontend (Client):
        STARTUP → AUTHENTICATING → READY → QUERYING/EXTENDED/COPY → READY → ...

    Backend (Server):
        STARTUP → AUTHENTICATING → READY → QUERYING/EXTENDED/COPY → READY → ...

    Either side can enter TERMINATED at any time by sending/receiving Terminate.
    Either side can enter FAILED at any time by receiving ErrorResponse.
    """

    # Initial state - waiting for or sending startup message
    STARTUP = auto()

    # SSL/GSS negotiation (optional)
    SSL_NEGOTIATION = auto()
    GSS_NEGOTIATION = auto()

    # Authentication loop
    AUTHENTICATING = auto()

    # SASL authentication sub-phases (decoder needs these to distinguish 'p' messages)
    AUTHENTICATING_SASL_INITIAL = auto()
    AUTHENTICATING_SASL_CONTINUE = auto()

    # Post-auth, waiting for BackendKeyData and ParameterStatus messages
    INITIALIZATION = auto()

    # Ready to accept queries
    READY = auto()

    # Simple query protocol active
    SIMPLE_QUERY = auto()

    # Extended query protocol active
    EXTENDED_QUERY = auto()

    # COPY mode (COPY IN, COPY OUT, or COPY BOTH)
    COPY_IN = auto()
    COPY_OUT = auto()
    COPY_BOTH = auto()

    # Function call active (legacy)
    FUNCTION_CALL = auto()

    # Connection terminated (after Terminate sent/received)
    TERMINATED = auto()

    # Connection failed (received ErrorResponse during startup/auth)
    FAILED = auto()


class ProtocolVersion(IntEnum):
    """PostgreSQL Protocol Versions."""

    V3_0 = 0x00030000  # Standard for PG 14-17
    V3_2 = 0x00030002  # New for PG 18+ (Variable length cancel keys)
    SSL_REQUEST = 80877103
    CANCEL_REQUEST = 80877102
    GSSENC_REQUEST = 80877104


class TransactionStatus(StrEnum):
    """Status returned in ReadyForQuery ('Z') messages."""

    IDLE = "I"
    IN_TRANSACTION = "T"
    ERROR_TRANSACTION = "E"


class FrontendMessageType(StrEnum):
    """Identifiers for messages sent by the Frontend (Client)."""

    BIND = "B"
    CLOSE = "C"
    COPY_DATA = "d"  # Shared
    COPY_DONE = "c"  # Shared
    COPY_FAIL = "f"
    DESCRIBE = "D"
    EXECUTE = "E"
    FLUSH = "H"
    FUNCTION_CALL = "F"
    PARSE = "P"
    PASSWORD = "p"  # Also used for GSS/SSPI/SASL responses
    QUERY = "Q"
    SYNC = "S"
    TERMINATE = "X"


class BackendMessageType(StrEnum):
    """Identifiers for messages sent by the Backend (Server)."""

    AUTHENTICATION = "R"
    BACKEND_KEY_DATA = "K"
    BIND_COMPLETE = "2"
    CLOSE_COMPLETE = "3"
    COMMAND_COMPLETE = "C"
    COPY_DATA = "d"  # Shared
    COPY_DONE = "c"  # Shared
    COPY_IN_RESPONSE = "G"
    COPY_OUT_RESPONSE = "H"
    COPY_BOTH_RESPONSE = "W"
    DATA_ROW = "D"
    EMPTY_QUERY_RESPONSE = "I"
    ERROR_RESPONSE = "E"
    FUNCTION_CALL_RESPONSE = "V"
    NEGOTIATE_PROTOCOL_VERSION = "v"
    NO_DATA = "n"
    NOTICE_RESPONSE = "N"
    NOTIFICATION_RESPONSE = "A"
    PARAMETER_DESCRIPTION = "t"
    PARAMETER_STATUS = "S"
    PARSE_COMPLETE = "1"
    PORTAL_SUSPENDED = "s"
    READY_FOR_QUERY = "Z"
    ROW_DESCRIPTION = "T"
