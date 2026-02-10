"""Scan message structures."""
import logging
from enum import Enum
import struct

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


class ScanActionStruct(base.NanonisMessage):
    """Scan Action struct."""

    action: int  # 2 bytes, unsigned int16
    direction: int  # 4 bytes, unsigned int32

    def format(self) -> str:
        """Override."""
        return 'HI'


class ScanActionCall(base.NanonisMessage):
    """Scan Action call."""

    def get_command_name(self) -> str:
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


class ScanStatusStruct(base.NanonisMessage):
    """Scan status struct."""

    status: int  # 4 bytes, unsigned int32

    def format(self) -> str:
        """Override."""
        return 'I'


class ScanStatusCall(base.NanonisMessage):
    """Scan status call."""

    def get_command_name(self) -> str:
        """Override."""
        return 'Scan.StatusGet'


class ScanStatusReq(base.EmptyRequest, ScanStatusCall):
    """Scan status request."""


class ScanStatusRep(base.NanonisResponse, ScanStatusCall, ScanStatusStruct):
    """Scan status response."""


# ----- Scan Frame ----- #
class ScanFrameStruct(base.NanonisMessage):
    """Scan frame struct.

    All attributes are in units of m (except angle which is deg).
    """

    center_x: float  # 4 bytes, float32
    center_y: float  # 4 bytes, float32
    width: float  # 4 bytes, float32
    height: float  # 4 bytes, float32
    angle: float  # 4 bytes, float32

    def format(self) -> str:
        """Override."""
        return 'fffff'


class ScanFrameSet(base.NanonisMessage):
    """Scan frame set call."""

    def get_command_name(self) -> str:
        """Override."""
        return 'Scan.FrameSet'


class ScanFrameSetReq(base.NanonisRequest, ScanFrameSet,
                      ScanFrameStruct):
    """Scan frame set request."""


class ScanFrameSetRep(base.EmptyResponse, ScanFrameSet):
    """Scan frame set response."""


class ScanFrameGet(base.NanonisMessage):
    """Scan frame get call."""

    def get_command_name(self) -> str:
        """Override."""
        return 'Scan.FrameGet'


class ScanFrameGetReq(base.EmptyRequest, ScanFrameGet):
    """Scan frame get request."""


class ScanFrameGetRep(base.NanonisResponse, ScanFrameGet,
                      ScanFrameStruct):
    """Scan frame get response."""


# ----- Scan Buffer ----- #
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

    num_channels: int  # 4 bytes, int32
    channel_indices: list[int]  # each value is 4 bytes, int32
    pixels: int  # 4 bytes, int32
    lines: int  # 4 bytes, int32

    def __init__(self, *args):
        """Override dataclass init to set up attributes properly."""
        self.num_channels = args[0]
        self.channel_indices = list(args[1:-2])
        self.pixels = args[-2]
        self.lines = args[-1]

    def format(self) -> str:
        """Override."""
        return 'i%diii' % (self.num_channels)


class ScanBufferSet(base.NanonisMessage):
    """Scan buffer set call."""

    def get_command_name(self) -> str:
        """Override."""
        return 'Scan.BufferSet'


class ScanBufferSetReq(base.NanonisRequest, ScanBufferSet,
                       ScanBufferStruct):
    """Scan buffer set request."""


class ScanBufferSetRep(base.EmptyResponse, ScanBufferSet):
    """Scan buffer set response."""


class ScanBufferGet(base.NanonisResponse):
    """Scan buffer get call."""

    def get_command_name(self) -> str:
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
        self.num_channels = struct.unpack_from('i', offset, buffer)
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


class ScanPropsStruct(base.NanonisMessage):
    """Scan props struct.

    NOTE:
    - due to variable string sizes, how we unpack from and pack to
    bytes arrays will be different.
    """

    continuous_scan: int = base.SettingState.NO_CHANGE  # 4 bytes, unsigned int32
    bouncy_scan: int = base.SettingState.NO_CHANGE  # 4 bytes, unsigned int32
    auto_save: int = base.SettingState.NO_CHANGE  # 4 bytes, unsigned int32
    name_size: int  # 4 bytes, int32
    base_name: str  # size defined by name_size
    comment_size: int  # 4 bytes, int32
    comment: str  # size defined by comment_size

    def format(self) -> str:
        """Override."""
        return 'IIIi%dsi%ds' % (self.name_size, self.comment_size)


class ScanPropsSet(base.NanonisMessage):
    """Scan props set call."""

    def get_command_name(self) -> str:
        """Override."""
        return 'Scan.PropsSet'


class ScanPropsSetReq(base.NanonisRequest, ScanPropsSet,
                      ScanPropsStruct):
    """Scan props set request."""


class ScanPropsSetRep(base.EmptyResponse, ScanPropsSet):
    """Scan props set response."""


class ScanPropsGet(base.NanonisResponse):
    """Scan props get call."""

    def get_command_name(self) -> str:
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
        __, __, __, self.name_size = struct.unpack_from('IIIi', offset, buffer)
        __, __, __, self.name_size, __, self.comment_size = struct.unpack_from(
            'IIIi%dsi', (self.name_size), offset, buffer)
        return self.format()


# ----- Scan Speed ----- #
class ScanSpeedConstant(Enum):
    """The manner in which linear and forward scans are kept constant."""

    NO_CHANGE = 0
    LINEAR_SPEED = 1
    TIME_PER_LINE = 2


class ScanSpeedStruct(base.NanonisMessage):
    """Scan speed struct.

    All units in m/s or s.
    speed_ratio defines the bwd_speed / fwd_speed ratio.
    """

    fwd_speed: float  # 4 bytes, float32
    bwd_speed: float  # 4 bytes, float32
    fwd_time_per_line: float  # 4 bytes, float32
    bwd_time_per_line: float  # 4 bytes, float32
    keep_parameter_constant: int  # 2 bytes, unsigned int16
    speed_ratio: float  # 4 bytes, float32

    def format(self) -> str:
        """Override."""
        return 'ffffHf'


class ScanSpeedSet(base.NanonisMessage):
    """Scan speed set call."""

    def get_command_name(self) -> str:
        """Override."""
        return 'Scan.SpeedSet'


class ScanSpeedSetReq(base.NanonisRequest, ScanSpeedSet,
                      ScanSpeedStruct):
    """Scan speed set request."""


class ScanSpeedSetRep(base.EmptyResponse, ScanSpeedSet):
    """Scan speed set response."""


class ScanSpeedGet(base.NanonisResponse):
    """Scan speed get call."""

    def get_command_name(self) -> str:
        """Override."""
        return 'Scan.SpeedGet'


class ScanSpeedGetReq(base.EmptyRequest, ScanSpeedGet):
    """Scan speed get request."""


class ScanSpeedGetRep(base.NanonisResponse, ScanSpeedGet,
                      ScanSpeedStruct):
    """Scan speed get request."""
