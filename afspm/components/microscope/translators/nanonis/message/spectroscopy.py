"""Spectroscopy message structures."""
import logging
from . import base


logger = logging.getLogger(__name__)


# ----- Spectra Start ----- #
class SpectraStart(base.NanonisMessage):
    """Spectroscopy start.

    NOTE: The channels to record must be set via the UI before using!
    """

    get_data: bool = 0  # 4 bytes, unsigned int32  (default False)
    name_size: int  # 4 bytes, int32
    base_name: str  # Size defined by name_size

    def format(self) -> str:
        """Override."""
        return 'Ii%ds' % (len(self.name_size),)


class SpectraStartReq(base.NanonisRequest, SpectraStart):
    """Spectroscopy start request."""

    def request_response(self) -> bool:
        """Not requesting response, in hopes we get asynchronous.

        The documentation implies that the full spectroscopy is returned,
        meaning it would need to be synchronous. We are hoping that, in
        *not* requesting a response, we get a quick asynchronous return.
        """
        return False


class BiasSpectraStart(SpectraStart):
    """Bias spectroscopy start."""

    def get_command_name(self) -> str:
        """Override."""
        return 'BiasSpectr.Start'


class BiasSpectraStartReq(BiasSpectraStart, SpectraStartReq):
    """Bias spectroscopy start request."""


class BiasSpectraStartRep(base.EmptyResponse):
    """Bias spectroscopy start request."""


class ZSpectraStart(SpectraStart):
    """Z spectroscopy start."""

    def get_command_name(self) -> str:
        """Override."""
        return 'ZSpectr.Start'


class ZSpectraStartReq(ZSpectraStart, SpectraStartReq):
    """Z spectroscopy start request."""


class ZSpectraStartRep(base.EmptyResponse):
    """Z spectroscopy start request."""


# ----- Spectra Stop ----- #
class BiasSpectraStopReq(base.EmptyRequest):
    """Bias spectroscopy stop request."""

    def get_command_name(self) -> str:
        """Override."""
        return 'BiasSpectr.Stop'


class BiasSpectrastopRep(base.EmptyResponse):
    """Bias spectroscopy stop response."""


class ZSpectraStopReq(base.EmptyRequest):
    """Z spectroscopy stop request."""

    def get_command_name(self) -> str:
        """Override."""
        return 'ZSpectr.Stop'


class ZSpectrastopRep(base.EmptyResponse):
    """Z spectroscopy stop response."""


# ----- Spectra Status ----- #
class SpectraStatusStruct(base.NanonisMessage):
    """Spectroscopy status."""

    status: int  # 4 bytes, unsigned int32

    def format(self) -> str:
        """Override."""
        return 'I'


class BiasSpectraStatusGet(base.NanonisMessage):
    """Bias spectroscopy status."""

    def get_command_name(self) -> str:
        """Override."""
        return 'BiasSpectr.StatusGet'


class ZSpectraStatusGet(base.NanonisMessage):
    """Z spectroscopy status."""

    def get_command_name(self) -> str:
        """Override."""
        return 'ZSpectr.StatusGet'


# TODO: Remember the name of what these are :(
# Anyway, matching the 'structure' of getter/setter commands for sake of
# consistency.
BiasSpectraStatusStruct = SpectraStatusStruct
ZSpectraStatusStruct = SpectraStatusStruct


class BiasSpectraStatusGetReq(BiasSpectraStatusGet, base.EmptyRequest):
    """Bias spectroscopy status request."""


class BiasSpectraStatusGetRep(BiasSpectraStatusGet, BiasSpectraStatusStruct):
    """Bias spectroscopy status request."""


class ZSpectraStatusGetReq(ZSpectraStatusGet, base.EmptyRequest):
    """Z spectroscopy status request."""


class ZSpectraStatusGetRep(ZSpectraStatusGet, ZSpectraStatusStruct):
    """Z spectroscopy status request."""
