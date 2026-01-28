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

import struct

from dataclasses import dataclass, replace
from abc import ABC, abstractmethod


logger = logging.getLogger(__name__)


# ----- Base Classes ----- #
@dataclass
class NanonisMessage(ABC):
    """Base class for Nanonis message.

    For getter/setter, it makes sense to put the data structure here,
    having the setter Req and the getter Rep inherit it.
    """

    @abstractmethod
    def get_command_name(self) -> str:
        """Get command name for calling."""

    @abstractmethod
    def format(self) -> str:
        """Return format of data structure."""


@dataclass
class NanonisResponse(ABC, NanonisMessage):
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

    def request_response(self) -> bool:
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

    status: int  # 4 bytes, unsigned int32
    description_size: int  # 4 bytes, int32
    description: str  # size defined by description_size

    def get_format(self, buffer: bytes, offset: int) -> str:
        """Override."""
        base_format = 'Ii'
        __, str_size = struct.unpack_from(base_format, offset, buffer)
        base_format += '%ds' % (str_size,)
        return base_format


# ----- Empty Req / Rep ----- #
class EmptyMessage(NanonisMessage):
    """Empty structure."""

    def format(self, buffer: bytes) -> str:
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

    command_name: str  # 4 bytes, str
    body_size: int  # 4 bytes, int32
    send_response: int  # 2 bytes, uint16
    # Empty: 2 bytes

    def format(self) -> str:
        """Override."""
        return '4siHxx'


@dataclass
class ResponseHeader(NanonisResponse):
    """Response header for any call."""

    command_name: str  # 4 bytes, str
    body_size: int  # 4 bytes, int32
    # Empty: 4 bytes

    def format(self) -> str:
        """Override."""
        return '4sixxxx'


# ----- Packing / Unpacking methods ----- #
class NanonisMessageError(Exception):
    """The parsed response indicates an error."""


def from_bytes(buffer: bytes, rep: NanonisResponse,
               requested_response: bool) -> NanonisResponse:
    """Populate NanonisResponse from bytes array and initialized response.

    Args:
        buffer: bytes array of received data.
        rep: NanonisResponse we expect, which we will populate.
        requested_response: whether or not we expected a response from the
            NanonisRequest linked to this NanonisResponse. You should be
            able to query the req.request_response() to get this attr.

    Returns:
        NanonisResponse of same type as rep, unpacked from buffer.

    Raises:
        NanonisMessageError if we requested a response and the response
            indicates an error.
    """
    rep_header = ResponseHeader()
    offset = struct.calcsize(rep_header.get_format())

    # Unpack response
    format = rep.get_format(buffer, offset)  # Get format for unpacking
    tuple_data = struct.unpack_from(format, offset, buffer)
    inst = replace(rep, *tuple_data)

    # Unpack error message (if expected)
    if requested_response:
        offset += struct.calcsize(format)
        format = ErrorRep.get_format(buffer, offset)
        tuple_data = struct.unpack_from(format, offset, buffer)
        error_rep = ErrorRep(*tuple_data)

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

    buffer = bytes()
    for this_req, offset in enumerate(
            (req_header, req),
            (0, struct.calcsize(req_header.format()))):
        format = this_req.get_format()
        local_buff = struct.pack_into(format, offset,
                                      *dataclass.astuple(this_req))
        buffer = buffer + local_buff
    return buffer
