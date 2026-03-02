from enum import IntEnum, StrEnum


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
