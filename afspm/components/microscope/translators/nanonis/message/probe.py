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

    x: float  # 8 bytes, float64
    y: float  # 8 bytes, float64

    @staticmethod
    def format() -> str:
        """Override."""
        return 'dd'


@dataclass
class XYPosSetStruct(XYPosStruct):
    """We add one attr for setting here."""

    # NOTE: We default to wait until the tip stops what it is doing.
    wait_end_of_move: bool = 1  # 4 bytes, unsigned int32

    @staticmethod
    def format() -> str:
        """Override."""
        return super().format() + 'I'


class XYPosSet(base.NanonisMessage):
    """XY pos set call."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'FolMe.XYPosSet'


class XYPosSetReq(base.NanonisRequest, XYPosSet,
                  XYPosStruct):
    """XY pos set request."""


class XYPosSetRep(base.EmptyResponse, XYPosSet):
    """XY pos set response."""


class XYPosGet(base.NanonisMessage):
    """XY pos get call."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'FolMe.XYPosGet'


# TODO: Whenever having attributes, we must declare it as a dataclass!!!
@dataclass
class XYPosGetReq(base.NanonisRequest, XYPosGet):
    """XY pos get request."""

    wait_for_newest_data: int  # 4 bytes, unsigned int32

    @staticmethod
    def format() -> str:
        """Override."""
        return 'I'


class XYPosGetRep(XYPosStruct, base.NanonisResponse, XYPosGet):
    """XY pos get request."""


# ----- SpeedSet ----- #
@dataclass
class SpeedStruct(base.NanonisMessage):
    """Speed struct.

    Custom speed set to 1 to ensure set distinguishes it from scan-speed
    (this is used for move-speed).

    Units are m/s
    """

    speed: float  # 4 bytes, float32
    custom_speed: bool = 1  # 4 bytes, unsigned int32

    @staticmethod
    def format() -> str:
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
