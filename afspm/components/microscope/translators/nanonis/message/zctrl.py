"""Z Control message structures."""
import logging
from . import base


logger = logging.getLogger(__name__)


# ----- ZCtrl Setpoint ----- #
class ZCtrlSetpointStruct(base.NanonisMessage):
    """Z-Control Setpoint."""

    value: float  # 4 bytes, float32

    def format(self) -> str:
        """Override."""
        return 'f'


class ZCtrlSetpointSet(base.NanonisMessage):
    """Z-Control Setpoint set."""

    def get_command_name(self) -> str:
        """Override."""
        return 'ZCtrl.SetpntSet'


class ZCtrlSetpointSetReq(base.NanonisRequest, ZCtrlSetpointSet,
                          ZCtrlSetpointStruct):
    """Z-Control Setpoint set request."""


class ZCtrlSetpointSetRep(base.EmptyResponse, ZCtrlSetpointSet):
    """Z-Control Setpoint set response."""


class ZCtrlSetpointGet(base.NanonisMessage):
    """Z-Control Setpoint get."""

    def get_command_name(self) -> str:
        """Override."""
        return 'ZCtrl.SetpntGet'


class ZCtrlSetpointGetReq(base.EmptyRequest, ZCtrlSetpointGet):
    """Z-Control Setpoint get request."""


class ZCtrlSetpointGetRep(base.NanonisResponse, ZCtrlSetpointGet,
                          ZCtrlSetpointStruct):
    """Z-Control Setpoint get response."""


# ----- ZCtrl Gain ----- #
class ZCtrlGainStruct(base.NanonisMessage):
    """Z-Control Gain."""

    proportional: float  # 4 bytes, float32
    time_constant: float  # 4 bytes, float32
    integral: float  # 4 bytes, float32

    def format(self) -> str:
        """Override."""
        return 'fff'


class ZCtrlGainSet(base.NanonisMessage):
    """Z-Control gain set."""

    def get_command_name(self) -> str:
        """Override."""
        return 'ZCtrl.GainSet'


class ZCtrlGainSetReq(base.NanonisRequest, ZCtrlGainSet,
                      ZCtrlGainStruct):
    """Z-Control Gain set request."""


class ZCtrlGainSetRep(base.EmptyResponse, ZCtrlGainSet):
    """Z-Control Gain set response."""


class ZCtrlGainGet(base.NanonisMessage):
    """Z-Control Gain get."""

    def get_command_name(self) -> str:
        """Override."""
        return 'ZCtrl.GainGet'


class ZCtrlGainGetReq(base.EmptyRequest, ZCtrlGainGet):
    """Z-Control Gain get request."""


class ZCtrlGainGetRep(base.NanonisResponse, ZCtrlGainGet,
                      ZCtrlGainStruct):
    """Z-Control Gain get response."""
