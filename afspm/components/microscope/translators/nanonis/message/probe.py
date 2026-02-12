"""Probe positioning message structures."""
import logging
from dataclasses import dataclass
from . import base


logger = logging.getLogger(__name__)


# ----- XY pos ----- #
@dataclass
class XYPosStruct(base.NanonisMessage):
    """XY pos struct.

    Units are m.
    """

    x: float = base.DEF_FLT  # 8 bytes, float64
    y: float = base.DEF_FLT  # 8 bytes, float64

    def format(self) -> str:
        """Override."""
        return 'dd'


class XYPosSet(base.NanonisMessage):
    """XY pos set call."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'FolMe.XYPosSet'


@dataclass
class XYPosSetReq(base.NanonisRequest, XYPosSet,
                  XYPosStruct):
    """XY pos set request.

    NOTE:
    - We default to wait until the tip stops what it is doing.
    """

    wait_end_of_move: bool = 1  # 4 bytes, unsigned int32

    def format(self) -> str:
        """Override."""
        return super().format() + 'I'


class XYPosSetRep(base.EmptyResponse, XYPosSet):
    """XY pos set response."""


class XYPosGet(base.NanonisMessage):
    """XY pos get call."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'FolMe.XYPosGet'


@dataclass
class XYPosGetReq(base.NanonisRequest, XYPosGet):
    """XY pos get request.

    NOTE:
    - We default to not waiting for newest data.
    """

    wait_for_newest_data: int = 0  # 4 bytes, unsigned int32

    def format(self) -> str:
        """Override."""
        return 'I'


class XYPosGetRep(base.NanonisResponse, XYPosGet, XYPosStruct):
    """XY pos get request."""


# ----- SpeedSet ----- #
@dataclass
class SpeedStruct(base.NanonisMessage):
    """Speed struct.

    Custom speed set to 1 ensures set distinguishes it from scan-speed
    (this is used for move-speed).

    Units are m/s.
    """

    speed: float = base.DEF_FLT  # 4 bytes, float32
    custom_speed: bool = 1  # 4 bytes, unsigned int32

    def format(self) -> str:
        """Override."""
        return 'fI'


class SpeedSet(base.NanonisMessage):
    """Speed set call."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'FolMe.SpeedSet'


class SpeedSetReq(base.NanonisRequest, SpeedSet,
                  SpeedStruct):
    """Speed set request."""


class SpeedSetRep(base.EmptyResponse, SpeedSet):
    """Speed set response."""


class SpeedGet(base.NanonisMessage):
    """Speed get call."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'FolMe.SpeedGet'


class SpeedGetReq(base.EmptyRequest, SpeedGet):
    """Speed get request."""


class SpeedGetRep(base.NanonisResponse, SpeedGet,
                  SpeedStruct):
    """Speed get request."""
