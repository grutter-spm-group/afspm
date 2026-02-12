"""Base Nanonis Message structures.

These structures (and the other ones in this directory) are set up
to match the message structures defined in the Nanonis TCP Protocol.
Via this protocol, one sends requests and receives responses, each of
which has a predefined header structure (RequestHeader, ResponseHeader).
For any request, one can specify whether or not a response is sent back.
By default, we set this to true for all requests. However, we exceptionally
*do not* request a response for spectroscopy start requests, as these return
the data itself. We thus assume this response is synchronous rather than
asynchronous (what we expect/desire).

TODO: EXPLAIN HOW packing/unpacking works here...

For logic that uses these, we expect for a name VARIABLE:
- VARIABLEStruct is the structure passed in a get/set call.
- VARIABLESet is the structure associated with a set.
- VARIABLEGet is the structure associated with a get.

Particularly, we use VARIABLE as the uuid in params.toml. From this, we can
instantiate the struct, request, and response as needed.
"""
import logging
import enum
import struct
from abc import ABC, abstractmethod

from dataclasses import dataclass, replace, fields, astuple


logger = logging.getLogger(__name__)


# --- Default vals --- #
DEF_FLT = float(0)  # Default to 0 to not interfere on setting.
DEF_STR = ''
DEF_INT = 0  # Default to 0 to not interfere on setting.


# ----- Common Strings ----- #
# Some common strings for our Nanonis controller message handling.
STRUCT = 'Struct'
GET_REQ = 'GetReq'
GET_REP = 'GetRep'
SET_REQ = 'SetReq'
SET_REP = 'SetRep'


# ----- Base Classes ----- #
class NanonisMessage(ABC):
    """Base class for Nanonis message.

    For getter/setter, it makes sense to put the data structure here,
    having the setter Req and the getter Rep inherit it.
    """

    @staticmethod
    @abstractmethod
    def get_command_name() -> str:
        """Get command name for calling."""

    @abstractmethod
    def format(self) -> str:
        """Return format of data structure."""


class NanonisResponse(NanonisMessage):
    """Base class for a Nanonis Response."""

    def get_format(self, buffer: bytes, offset: int) -> str:
        """Return the bytes format of the message.

        Note that in cases where the response contains a string,
        we need the buffer to determine the size of the string.
        Thus, we need to pass the buffer we have received to
        determine the full format.

        The buffer also contains the response header, so we need
        to provide the offset of this, to skip it when unpacking.

        Default is to just return format().

        Args:
            buffer: bytes array of received message.
            offset: offset in bytes array where to start unpacking.

        Returns:
            str: formatting for struct to unpack.
        """
        return self.format()


class NanonisRequest(NanonisMessage):
    """Nanonis request message."""

    @staticmethod
    def request_response() -> bool:
        """Whether or not we want this message to request for a response.

        Defaults to True.
        """
        return True

    def get_format(self) -> str:
        """Return the bytes format of the message.

        For the request, we should not need any buffer. We are using
        this data structure to *create* the buffer!

        Default is to return format().
        """
        return self.format()


@dataclass
class ErrorRep(NanonisResponse):
    """Nanonis error portion of response."""

    status: int = DEF_INT  # 4 bytes, unsigned int32
    description_size: int = DEF_INT  # 4 bytes, int32
    description: str = DEF_STR  # size defined by description_size

    def get_format(cls, buffer: bytes, offset: int) -> str:
        """Override."""
        base_format = 'Ii'
        __, str_size = struct.unpack_from(base_format, buffer, offset)
        base_format += '%ds' % (str_size,)
        return base_format

    @staticmethod
    def get_command_name() -> str:
        """Override. Empty because not applicable."""
        return ''

    def format(self) -> str:
        """Override. Empty because get_format is overriden."""
        return ''


# ----- Empty Req / Rep ----- #
class EmptyMessage(NanonisMessage):
    """Empty structure."""

    def format(self) -> str:
        """Override."""
        return ''


class EmptyRequest(NanonisRequest, EmptyMessage):
    """Empty request."""


class EmptyResponse(NanonisResponse, EmptyMessage):
    """Empty response."""


# ----- Request / Response Headers ----- #
@dataclass
class RequestHeader(NanonisRequest):
    """Request header for any call."""

    command_name: str = DEF_STR  # 32 bytes, str
    body_size: int = DEF_INT  # 4 bytes, int32
    send_response: int = DEF_INT  # 2 bytes, uint16
    # Empty: 2 bytes

    def format(self) -> str:
        """Override."""
        return '32siHxx'

    @staticmethod
    def get_command_name() -> str:
        """Override, not used."""
        return ''


@dataclass
class ResponseHeader(NanonisResponse):
    """Response header for any call."""

    command_name: str = DEF_STR  # 32 bytes, str
    body_size: int = DEF_INT  # 4 bytes, int32
    # Empty: 4 bytes

    def format(self) -> str:
        """Override."""
        return '32sixxxx'

    @staticmethod
    def get_command_name() -> str:
        """Override, not used."""
        return ''


# ----- Packing / Unpacking methods ----- #
class NanonisMessageError(Exception):
    """The parsed response indicates an error."""


BIG_ENDIAN = '>'  # To force big-endian encoding everywhere


# TODO: loop this so it is less ugly.
def from_bytes(buffer: bytes, rep: NanonisResponse) -> NanonisResponse:
    """Populate NanonisResponse from bytes array and initialized response.

    Args:
        buffer: bytes array of received data.
        rep: NanonisResponse we expect, which we will populate.

    Returns:
        NanonisResponse of same type as rep, unpacked from buffer.

    Raises:
        NanonisMessageError if we requested a response and the response
            indicates an error.
    """
    # Unpack header
    offset = 0
    rep_header = ResponseHeader()
    format = BIG_ENDIAN + rep_header.format()
    tuple_data = struct.unpack_from(format, buffer, offset)
    # Extract attributes as list, converting str to utf-8 encoded bytes
    tuple_data = [t.decode('utf-8') if isinstance(t, str) else t
                  for t in tuple_data]

    # Unpack response (get format for unpacking)
    offset = struct.calcsize(rep_header.format())
    format = BIG_ENDIAN + rep.get_format(buffer, offset)
    tuple_data = struct.unpack_from(format, buffer, offset)
    # Extract attributes as list, converting str to utf-8 encoded bytes
    tuple_data = [t.decode('utf-8') if isinstance(t, str) else t
                  for t in tuple_data]

    # Update struct with proper values
    inst = replace(rep, **dict(zip([f.name for f in fields(rep)], tuple_data)))

    # Unpack error message
    offset += struct.calcsize(format)
    error_rep = ErrorRep()
    format = BIG_ENDIAN + error_rep.get_format(buffer, offset)
    tuple_data = struct.unpack_from(format, buffer, offset)
    # Extract attributes as list, converting str to utf-8 encoded bytes
    tuple_data = [t.decode('utf-8') if isinstance(t, str) else t
                  for t in tuple_data]
    error_rep = ErrorRep(*tuple_data)  # TODO: use replace from above!

    if error_rep.status:  # Error occurred
        msg = (f"Error for {type(inst).__name__} message:"
               f"{error_rep.description}")
        logger.error(msg)
        logger.error(inst)
        raise NanonisMessageError(msg)
    return inst


def to_bytes(req: NanonisRequest) -> bytes:
    """Create bytes array from NanonisRequest."""
    req_header = RequestHeader(
        req.get_command_name(),
        struct.calcsize(req.get_format()),  # Body size from request format
        req.request_response())

    buffer = bytearray()
    for this_req, offset in zip(
            (req_header, req),
            (0, struct.calcsize(req_header.format()))):
        format = BIG_ENDIAN + this_req.get_format()
        # Extract attributes as list, converting str to utf-8 encoded bytes
        data = [t.encode('utf-8') if isinstance(t, str) else t
                for t in astuple(this_req)]
        local_buff = struct.pack(format, *data)
        buffer = buffer + local_buff
    return buffer


@dataclass
class NanonisReqRep:
    """Holds the various request-reply associatd with a Nanonis call.

    For a given data structure Nanonis has bundled you can request it and
    receive a reply. This structure holds that.
    """

    req: NanonisRequest
    rep: NanonisResponse


class SettingState(enum.Enum):
    """Setting state for scan/spectra props."""

    NO_CHANGE = 0
    ON = 1
    OFF = 2
