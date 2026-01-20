"""Probe positioning message structures."""
import logging
from . import base


logger = logging.getLogger(__name__)


# ----- XY pos ----- #
class XYPosStruct(base.NanonisMessage):
    """XY pos struct.

    Units are m.
    """

    x: float  # 8 bytes, float64
    y: float  # 8 bytes, float64
    wait_end_of_move: bool  # 4 bytes, unsigned int32

    def format(self) -> str:
        """Override."""
        return 'ddI'


class XYPosSet(base.NanonisMessage):
    """XY pos set call."""

    def get_command_name(self) -> str:
        """Override."""
        return 'FolMe.XYPosSet'


class XYPosSetReq(base.NanonisRequest, XYPosSet,
                  XYPosStruct):
    """XY pos set request."""


class XYPosSetRep(base.EmptyResponse, XYPosSet):
    """XY pos set response."""


class XYPosGet(base.NanonisResponse):
    """XY pos get call."""

    def get_command_name(self) -> str:
        """Override."""
        return 'FolMe.XYPosGet'


class XYPosGetReq(base.EmptyRequest, XYPosGet):
    """XY pos get request."""


class XYPosGetRep(base.NanonisResponse, XYPosGet,
                  XYPosStruct):
    """XY pos get request."""


# ----- SpeedSet ----- #
class SpeedStruct(base.NanonisMessage):
    """Speed struct.

    Units are m/s
    """

    speed: float  # 4 bytes, float32
    custom_speed: bool  # 4 bytes, unsigned int32

    def format(self) -> str:
        """Override."""
        return 'fI'


class SpeedSet(base.NanonisMessage):
    """Speed set call."""

    def get_command_name(self) -> str:
        """Override."""
        return 'FolMe.SpeedSet'


class SpeedSetReq(base.NanonisRequest, SpeedSet,
                  SpeedStruct):
    """Speed set request."""


class SpeedSetRep(base.EmptyResponse, SpeedSet):
    """Speed set response."""


class SpeedGet(base.NanonisResponse):
    """Speed get call."""

    def get_command_name(self) -> str:
        """Override."""
        return 'FolMe.SpeedGet'


class SpeedGetReq(base.EmptyRequest, SpeedGet):
    """Speed get request."""


class SpeedGetRep(base.NanonisResponse, SpeedGet,
                  SpeedStruct):
    """Speed get request."""
