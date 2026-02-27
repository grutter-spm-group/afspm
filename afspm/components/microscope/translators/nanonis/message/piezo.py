"""Pizeo message structures."""
import logging
from dataclasses import dataclass
from . import base


logger = logging.getLogger(__name__)


@dataclass
class PiezoTiltStruct(base.NanonisMessage):
    """Piezo tilt struct.

    Units are in deg.
    """

    tilt_x: float = base.DEF_FLT  # 4 bytes, float32
    tilt_y: float = base.DEF_FLT  # 4 bytes, float32

    def format(self) -> str:
        """Override."""
        return 'ff'


class PiezoTiltSet(base.NanonisMessage):
    """PiezoTilt set."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'Piezo.TiltSet'


class PiezoTiltSetReq(base.NanonisRequest, PiezoTiltStruct, PiezoTiltSet):
    """PiezoTilt set request."""


class PiezoTiltSetRep(base.EmptyResponse, PiezoTiltSet):
    """PiezoTilt set response."""


class PiezoTiltGet(base.NanonisMessage):
    """PiezoTilt get."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'Piezo.TiltGet'


class PiezoTiltGetReq(base.EmptyRequest, PiezoTiltGet):
    """PiezoTilt getter request."""


class PiezoTiltGetRep(base.NanonisResponse, PiezoTiltStruct, PiezoTiltGet):
    """PiezoTilt getter response."""
