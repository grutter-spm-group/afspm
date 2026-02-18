"""Scan message structures."""
import logging
from dataclasses import dataclass, field
from enum import Enum
import struct
from typing import Any

from . import base


logger = logging.getLogger(__name__)


# ----- Scan Action ----- #
class ScanAction(Enum):
    """Scan status."""

    START = 0
    STOP = 1
    PAUSE = 2
    RESUME = 3


class ScanDirection(Enum):
    """Scan direction."""

    UP = 0
    DOWN = 1


@dataclass
class ScanActionStruct(base.NanonisMessage):
    """Scan Action struct.

    NOTE:
    - We default to non-sensical attribute values to ensure we are properly
    parsing get() calls.
    """

    action: int = -1  # 2 bytes, unsigned int16
    direction: int = -1  # 4 bytes, unsigned int32

    def format(self) -> str:
        """Override."""
        return 'HI'


class ScanActionCall(base.NanonisMessage):
    """Scan Action call."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'Scan.Action'


class ScanActionReq(base.NanonisRequest, ScanActionCall, ScanActionStruct):
    """Scan Action request."""


class ScanActionRep(base.EmptyResponse, ScanActionCall):
    """Scan Action response."""


# ---- Scan Status ----- #
class ScanStatus(Enum):
    """Scan Status."""

    NOT_RUNNING = 0
    RUNNING = 1


@dataclass
class ScanStatusStruct(base.NanonisMessage):
    """Scan status struct.

    NOTE:
    - We default to a non-sensical value to ensure we are properly parsing
    get() calls.
    """

    status: int = -1  # 4 bytes, unsigned int32

    def format(self) -> str:
        """Override."""
        return 'I'


class ScanStatusCall(base.NanonisMessage):
    """Scan status call."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'Scan.StatusGet'


class ScanStatusGetReq(base.EmptyRequest, ScanStatusCall):
    """Scan status request."""


class ScanStatusGetRep(base.NanonisResponse, ScanStatusCall, ScanStatusStruct):
    """Scan status response."""


# ----- Scan Frame ----- #
@dataclass
class ScanFrameStruct(base.NanonisMessage):
    """Scan frame struct.

    All attributes are in units of m (except angle which is deg).
    """

    center_x: float = base.DEF_FLT  # 4 bytes, float32
    center_y: float = base.DEF_FLT  # 4 bytes, float32
    width: float = base.DEF_FLT  # 4 bytes, float32
    height: float = base.DEF_FLT  # 4 bytes, float32
    angle: float = base.DEF_FLT  # 4 bytes, float32

    def format(self) -> str:
        """Override."""
        return 'fffff'


class ScanFrameSet(base.NanonisMessage):
    """Scan frame set call."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'Scan.FrameSet'


class ScanFrameSetReq(base.NanonisRequest, ScanFrameSet,
                      ScanFrameStruct):
    """Scan frame set request."""


class ScanFrameSetRep(base.EmptyResponse, ScanFrameSet):
    """Scan frame set response."""


class ScanFrameGet(base.NanonisMessage):
    """Scan frame get call."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'Scan.FrameGet'


class ScanFrameGetReq(base.EmptyRequest, ScanFrameGet):
    """Scan frame get request."""


class ScanFrameGetRep(base.NanonisResponse, ScanFrameGet,
                      ScanFrameStruct):
    """Scan frame get response."""


# ----- Scan Buffer ----- #
@dataclass
class ScanBufferStruct(base.NanonisMessage):
    """Scan buffer struct.

    NOTE:
    - for this struct, the size of channel_indices is dependent
    on num_channels. This will change how we unpack from and pack to
    bytes arrays.
    - pixels is 'coerced' to closest multiple of 16!
    - if lines is 0 and 'maintain aspect ratio' button is selected in UI,
    it will choose lines to keep prior aspect ratio.
    """

    num_channels: int = base.DEF_INT  # 4 bytes, int32
    # each value is 4 bytes, int32
    channel_indices: list[int] = field(default_factory=list)
    pixels: int = base.DEF_INT  # 4 bytes, int32
    lines: int = base.DEF_INT  # 4 bytes, int32

    def __post__init(self):
        assert len(self.channel_indices) == self.num_channels

    def format(self) -> str:
        """Override."""
        return 'i%diii' % (self.num_channels)

    def create_data_dict(self, tuple_data: tuple[Any]
                         ) -> dict[str, Any]:
        """Override due to channel_indices.

        Because our tuple is of the form:
        (num_channels, channel_indices[0], ..., channel_indices[-1], ... )

        (i.e., the channel_indices are not pre-packed in their own iterable),
        we need to manually pack them here.
        """
        num_channels = tuple_data[0]
        channel_indices = list(tuple_data[1:-2])
        pixels = tuple_data[-2]
        lines = tuple_data[-1]

        new_tuple_data = (num_channels, channel_indices, pixels, lines)
        return super().create_data_dict(new_tuple_data)


class ScanBufferSet(base.NanonisMessage):
    """Scan buffer set call."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'Scan.BufferSet'


class ScanBufferSetReq(base.NanonisRequest, ScanBufferSet,
                       ScanBufferStruct):
    """Scan buffer set request."""


class ScanBufferSetRep(base.EmptyResponse, ScanBufferSet):
    """Scan buffer set response."""


class ScanBufferGet(base.NanonisMessage):
    """Scan buffer get call."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'Scan.BufferGet'


class ScanBufferGetReq(base.EmptyRequest, ScanBufferGet):
    """Scan buffer get request."""


class ScanBufferGetRep(base.NanonisResponse, ScanBufferGet,
                       ScanBufferStruct):
    """Scan buffer get response.

    NOTE:
    - channel_indices is variable, so our get_format() is custom.
    """

    def get_format(self, buffer: bytes, offset: int) -> str:
        """Override due to variable channel_indices."""
        self.num_channels = struct.unpack_from('i', buffer, offset)
        return self.format()


# ----- Scan Props ----- $
class ScanSettingStatus(Enum):
    """Status for scan setting (continuous or bouncy scan settings)."""

    NO_CHANGE = 0
    ON = 1
    OFF = 2


class AutoSaveStatus(Enum):
    """Auto-save status."""

    NO_CHANGE = 0
    ALL = 1
    NEXT = 2
    OFF = 3


@dataclass
class ScanPropsStruct(base.NanonisMessage):
    """Scan props struct.

    NOTE:
    - due to variable string sizes, how we unpack from and pack to
    bytes arrays will be different.
    - We default base_name to '' to try and avoid changing it. Same with
    comment.
    """

    continuous_scan: int = base.SettingState.NO_CHANGE  # 4 bytes, unsigned int32
    bouncy_scan: int = base.SettingState.NO_CHANGE  # 4 bytes, unsigned int32
    auto_save: int = base.SettingState.NO_CHANGE  # 4 bytes, unsigned int32
    name_size: int = base.DEF_INT  # 4 bytes, int32
    base_name: str = base.DEF_STR  # size defined by name_size
    comment_size: int = base.DEF_INT  # 4 bytes, int32
    comment: str = base.DEF_STR  # size defined by comment_size

    def format(self) -> str:
        """Override."""
        return 'IIIi%dsi%ds' % (self.name_size, self.comment_size)


class ScanPropsSet(base.NanonisMessage):
    """Scan props set call."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'Scan.PropsSet'


class ScanPropsSetReq(base.NanonisRequest, ScanPropsSet,
                      ScanPropsStruct):
    """Scan props set request."""


class ScanPropsSetRep(base.EmptyResponse, ScanPropsSet):
    """Scan props set response."""


class ScanPropsGet(base.NanonisMessage):
    """Scan props get call."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'Scan.PropsGet'


class ScanPropsGetReq(base.EmptyRequest, ScanPropsGet):
    """Scan props get request."""


class ScanPropsGetRep(base.NanonisResponse, ScanPropsGet,
                      ScanPropsStruct):
    """Scan props get response.

    NOTE:
    - base_name and comment are variable, so our get_format() is custom.
    """

    def get_format(self, buffer: bytes, offset: int) -> str:
        """Override due to variable channel_indices."""
        __, __, __, self.name_size = struct.unpack_from('IIIi', buffer, offset)
        __, __, __, self.name_size, __, self.comment_size = struct.unpack_from(
            'IIIi%dsi', (self.name_size), buffer, offset)
        return self.format()


# ----- Scan Speed ----- #
class ScanSpeedConstant(Enum):
    """The manner in which linear and forward scans are kept constant."""

    NO_CHANGE = 0
    LINEAR_SPEED = 1
    TIME_PER_LINE = 2


@dataclass
class ScanSpeedStruct(base.NanonisMessage):
    """Scan speed struct.

    All units in m/s or s.
    speed_ratio defines the bwd_speed / fwd_speed ratio.
    """

    fwd_speed: float = base.DEF_FLT  # 4 bytes, float32
    bwd_speed: float = base.DEF_FLT  # 4 bytes, float32
    fwd_time_per_line: float = base.DEF_FLT  # 4 bytes, float32
    bwd_time_per_line: float = base.DEF_FLT  # 4 bytes, float32
    keep_parameter_constant: int = base.DEF_INT  # 2 bytes, unsigned int16
    speed_ratio: float = base.DEF_FLT  # 4 bytes, float32

    def format(self) -> str:
        """Override."""
        return 'ffffHf'


class ScanSpeedSet(base.NanonisMessage):
    """Scan speed set call."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'Scan.SpeedSet'


class ScanSpeedSetReq(base.NanonisRequest, ScanSpeedSet,
                      ScanSpeedStruct):
    """Scan speed set request."""


class ScanSpeedSetRep(base.EmptyResponse, ScanSpeedSet):
    """Scan speed set response."""


class ScanSpeedGet(base.NanonisMessage):
    """Scan speed get call."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'Scan.SpeedGet'


class ScanSpeedGetReq(base.EmptyRequest, ScanSpeedGet):
    """Scan speed get request."""


class ScanSpeedGetRep(base.NanonisResponse, ScanSpeedGet,
                      ScanSpeedStruct):
    """Scan speed get request."""
