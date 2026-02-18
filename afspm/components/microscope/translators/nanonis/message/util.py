"""Util structures."""
import logging
from dataclasses import dataclass
import struct
from . import base


logger = logging.getLogger(__name__)


@dataclass
class SessionPathStruct(base.NanonisMessage):
    """Session path: dir where files are saved."""

    session_path_size: int = base.DEF_INT  # 4 bytes, int32
    session_path: str = base.DEF_STR  # Size defined by name_size

    def format(self) -> str:
        """Override."""
        return 'i%ds' % (self.session_path_size)


class SessionPathGet(base.NanonisMessage):
    """Session path getter."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'Util.SessionPathGet'


class SessionPathGetReq(base.EmptyRequest, SessionPathGet):
    """Session path get request."""


class SessionPathGetRep(base.NanonisResponse, SessionPathGet,
                        SessionPathStruct):
    """Session path get response.

    NOTE:
    session_path is variable, so our get_format() is custom.
    """

    def get_format(self, buffer: bytes, offset: int) -> str:
        """Override due to variable session_path."""
        format = base.BIG_ENDIAN + 'i'
        self.session_path_size = struct.unpack_from(format, buffer, offset)
        return self.format()
