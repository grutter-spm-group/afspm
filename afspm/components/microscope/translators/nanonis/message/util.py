"""Util structures."""
import logging
from . import base


logger = logging.getLogger(__name__)


class SessionPathStruct(base.NanonisMessage):
    """Session path: dir where files are saved."""

    session_path_size: int  # 4 bytes, int32
    session_path: str  # Size defined by name_size


class SessionPathGet(base.NanonisMessage):
    """Session path getter."""

    def get_command_name(self) -> str:
        """Override."""
        return 'Util.SessionPathGet'


class SessionPathGetReq(base.EmptyRequest, SessionPathGet):
    """Session path get request."""


class SessionPathGetRep(base.NanonisResponse, SessionPathGet,
                        SessionPathStruct):
    """Session path get response."""
