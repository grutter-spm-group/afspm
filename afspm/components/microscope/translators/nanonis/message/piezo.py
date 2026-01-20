"""Pizeo message structures."""
import logging
from . import base


logger = logging.getLogger(__name__)


class PiezoTiltStruct(base.NanonisMessage):
    """Piezo tilt struct.

    Units are in deg.
    """

    tilt_x: float  # 4 bytes, float32
    tilt_y: float  # 4 bytes, float32

    def format(self) -> str:
        """Override."""
        return 'ff'


class PiezoTiltSet(base.NanonisMessage):
    """PiezoTilt set."""

    def get_command_name(self) -> str:
        """Override."""
        return 'Piezo.TiltSet'


class PiezoTiltSetReq(base.NanonisRequest, PiezoTiltStruct, PiezoTiltSet):
    """PiezoTilt set request."""


class PiezoTiltSetRep(base.EmptyResponse, PiezoTiltSet):
    """PiezoTilt set response."""


class PiezoTiltGet(base.NanonisMessage):
    """PiezoTilt get."""

    def get_command_name(self) -> str:
        """Override."""
        return 'Piezo.TiltGet'


class PiezoTiltGetReq(base.EmptyRequest, PiezoTiltGet):
    """PiezoTilt getter request."""


class PiezoTiltGetRep(base.NanonisResponse, PiezoTiltStruct, PiezoTiltGet):
    """PiezoTilt getter response."""
