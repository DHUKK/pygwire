"""Authentication messages (both frontend and backend)."""

from __future__ import annotations

import struct
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, Self

from pygwire.constants import BackendMessageType, FrontendMessageType

from ._base import (
    BackendMessage,
    FrontendMessage,
    ProtocolError,
    _read_cstring,
    register,
)

# ---------------------------------------------------------------------------
# Struct helpers (pre-compiled for hot-path parsing)
# ---------------------------------------------------------------------------
_INT32 = struct.Struct("!I")  # unsigned 32-bit, network byte order
_SINT32 = struct.Struct("!i")  # signed 32-bit (NULL parameter sentinel -1)


# ═══════════════════════════════════════════════════════════════════════════
# SSLResponse — single-byte reply to SSLRequest (not a regular message)
# ═══════════════════════════════════════════════════════════════════════════


class SSLResponse(Enum):
    """Server's single-byte reply to an SSLRequest."""

    SUPPORTED = b"S"
    NOT_SUPPORTED = b"N"

    @classmethod
    def from_bytes(cls, data: bytes) -> SSLResponse:
        try:
            return cls(data)
        except ValueError:
            raise ProtocolError(f"Unexpected SSL response byte: {data!r}") from None


# ═══════════════════════════════════════════════════════════════════════════
# Backend Authentication family ('R')
# ═══════════════════════════════════════════════════════════════════════════
# All share identifier 'R'. We register a dispatcher class that fans out
# to concrete types based on the Int32 auth code.


@dataclass(slots=True)
class AuthenticationBase(BackendMessage):
    """Base class for all Authentication sub-messages.

    All authentication messages share the 'R' identifier and are distinguished
    by an Int32 auth code in the payload. Concrete subclasses include
    ``AuthenticationOk``, ``AuthenticationMD5Password``, ``AuthenticationSASL``, etc.
    """

    identifier: ClassVar[bytes] = b"R"
    auth_code: ClassVar[int] = 0

    def encode(self) -> bytes:
        return _INT32.pack(self.auth_code)


_AUTH_SUBTYPE_REGISTRY: dict[int, type[AuthenticationBase]] = {}


def _register_auth(code: int) -> Callable[[type[AuthenticationBase]], type[AuthenticationBase]]:
    """Register an Authentication sub-type for a given Int32 auth code."""

    def decorator(cls: type[AuthenticationBase]) -> type[AuthenticationBase]:
        cls.auth_code = code
        _AUTH_SUBTYPE_REGISTRY[code] = cls
        return cls

    return decorator


@register(BackendMessageType.AUTHENTICATION)
@dataclass(slots=True)
class Authentication(AuthenticationBase):
    """Dispatcher for Authentication ('R') messages.

    ``decode`` inspects the first Int32 (auth code) and delegates to the
    appropriate sub-type.  The concrete instance returned is *always* the
    specific sub-class (e.g. ``AuthenticationOk``).
    """

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        (code,) = _INT32.unpack_from(payload)
        sub_cls = _AUTH_SUBTYPE_REGISTRY.get(code)
        if sub_cls is None:
            raise ProtocolError(f"Unknown authentication code: {code}")
        return sub_cls.decode(payload)  # type: ignore[return-value]


# -- Concrete authentication sub-types ------------------------------------


@_register_auth(0)
@dataclass(slots=True)
class AuthenticationOk(AuthenticationBase):
    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()


@_register_auth(2)
@dataclass(slots=True)
class AuthenticationKerberosV5(AuthenticationBase):
    """AuthenticationKerberosV5 — request Kerberos V5 authentication (deprecated)."""

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()


@_register_auth(3)
@dataclass(slots=True)
class AuthenticationCleartextPassword(AuthenticationBase):
    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()


@_register_auth(5)
@dataclass(slots=True)
class AuthenticationMD5Password(AuthenticationBase):
    salt: bytes = b"\x00\x00\x00\x00"

    def encode(self) -> bytes:
        return _INT32.pack(self.auth_code) + self.salt

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        salt = bytes(payload[4:8])
        return cls(salt=salt)


@_register_auth(7)
@dataclass(slots=True)
class AuthenticationGSS(AuthenticationBase):
    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()


@_register_auth(8)
@dataclass(slots=True)
class AuthenticationGSSContinue(AuthenticationBase):
    data: bytes = b""

    def encode(self) -> bytes:
        return _INT32.pack(self.auth_code) + self.data

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls(data=bytes(payload[4:]))


@_register_auth(9)
@dataclass(slots=True)
class AuthenticationSSPI(AuthenticationBase):
    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls()


@_register_auth(10)
@dataclass(slots=True)
class AuthenticationSASL(AuthenticationBase):
    mechanisms: list[str] = field(default_factory=list)

    def encode(self) -> bytes:
        buf = bytearray(_INT32.pack(self.auth_code))
        for mech in self.mechanisms:
            buf.extend(mech.encode("utf-8"))
            buf.append(0)
        buf.append(0)  # final null terminator
        return bytes(buf)

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        offset = 4  # skip auth code
        mechanisms: list[str] = []
        while offset < len(payload):
            if payload[offset] == 0:
                break  # hit the final null terminator
            mech, offset = _read_cstring(payload, offset)
            mechanisms.append(mech)
        return cls(mechanisms=mechanisms)


@_register_auth(11)
@dataclass(slots=True)
class AuthenticationSASLContinue(AuthenticationBase):
    data: bytes = b""

    def encode(self) -> bytes:
        return _INT32.pack(self.auth_code) + self.data

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls(data=bytes(payload[4:]))


@_register_auth(12)
@dataclass(slots=True)
class AuthenticationSASLFinal(AuthenticationBase):
    data: bytes = b""

    def encode(self) -> bytes:
        return _INT32.pack(self.auth_code) + self.data

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls(data=bytes(payload[4:]))


# ═══════════════════════════════════════════════════════════════════════════
# Frontend Authentication response ('p')
# ═══════════════════════════════════════════════════════════════════════════
# The 'p' identifier is shared by PasswordMessage, SASLInitialResponse,
# and SASLResponse.  PostgreSQL reuses this identifier for different message
# types based on authentication phase context.
#
# **Registry Design:**
# Only PasswordMessage is registered via @register. When the codec sees 'p',
# it always decodes as PasswordMessage. SASLInitialResponse and SASLResponse
# are NOT registered — they exist solely as encoding helpers with structured
# fields for convenience when sending SASL messages.
#
# **Why this works:**
# - PasswordMessage.decode() is flexible enough to handle all 'p' variants
#   (cleartext, MD5, GSSAPI, SSPI, SASL) by storing str or bytes.
# - For *encoding*, use the specific class for clarity and correct structure:
#     msg = SASLInitialResponse(mechanism="SCRAM-SHA-256", data=...)
# - For *decoding*, the codec returns PasswordMessage and the application
#   determines the actual type from protocol context (auth phase).
#
# This design keeps the codec simple (one identifier → one registered class)
# while providing structured, self-documenting message types for encoding.


@register(FrontendMessageType.PASSWORD)
@dataclass(slots=True)
class PasswordMessage(FrontendMessage):
    """PasswordMessage ('p') — password response (cleartext or MD5-hashed).

    Also used for GSSAPI, SSPI, and SASL response messages. The exact message
    type can be deduced from the context (per PostgreSQL protocol docs).

    The password field accepts both str (for cleartext/MD5) and bytes (for
    SASL/GSSAPI/SSPI binary data).

    **Security Note:**
    Cleartext passwords are held in Python strings which are interned and
    cannot be securely erased in CPython. Users handling sensitive password
    data through this codec should be aware of this inherent limitation of
    the Python runtime.
    """

    password: str | bytes = ""

    def encode(self) -> bytes:
        if isinstance(self.password, bytes):
            # SASL/GSSAPI/SSPI binary data - return as-is
            return self.password
        # Cleartext/MD5 password - null-terminated string
        return self.password.encode("utf-8") + b"\x00"

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        # Try to read as null-terminated string (cleartext/MD5)
        # If no null terminator found, it's SASL/GSSAPI/SSPI binary data
        try:
            pwd, _ = _read_cstring(payload, 0)
            return cls(password=pwd)
        except ProtocolError:
            # No null terminator - store as binary data
            return cls(password=bytes(payload))


@dataclass(slots=True)
class SASLInitialResponse(FrontendMessage):
    """SASLInitialResponse ('p') — first SASL message from client.

    **Not registered**: This class is NOT registered in the message registry.
    The codec always decodes 'p' as PasswordMessage. This class exists to
    provide a structured, self-documenting way to *encode* SASL initial
    responses with proper field names instead of manual byte manipulation.

    Format:
        String — mechanism name
        Int32  — length of client-first-message (-1 if absent)
        Byte[n] — client-first-message data
    """

    identifier: ClassVar[bytes] = b"p"
    mechanism: str = ""
    data: bytes = b""

    def encode(self) -> bytes:
        buf = bytearray()
        buf.extend(self.mechanism.encode("utf-8"))
        buf.append(0)
        if self.data:
            buf.extend(_INT32.pack(len(self.data)))
            buf.extend(self.data)
        else:
            buf.extend(_SINT32.pack(-1))
        return bytes(buf)

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        mechanism, offset = _read_cstring(payload, 0)
        (data_len,) = _SINT32.unpack_from(payload, offset)
        offset += 4
        data = b"" if data_len == -1 else bytes(payload[offset : offset + data_len])
        return cls(mechanism=mechanism, data=data)


@dataclass(slots=True)
class SASLResponse(FrontendMessage):
    """SASLResponse ('p') — subsequent SASL message from client.

    **Not registered**: This class is NOT registered in the message registry.
    The codec always decodes 'p' as PasswordMessage. This class exists to
    provide a structured, self-documenting way to *encode* SASL continuation
    responses instead of using PasswordMessage directly.

    Format:
        Byte[n] — SASL data (entire payload)
    """

    identifier: ClassVar[bytes] = b"p"
    data: bytes = b""

    def encode(self) -> bytes:
        return self.data

    @classmethod
    def decode(cls, payload: memoryview) -> Self:
        return cls(data=bytes(payload))
