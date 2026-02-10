"""Spectroscopy message structures."""
import logging
import enum
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


# Pseudonyms for consistency
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


class SpectraPropsStruct(base.NanonisMessage):
    """Spectroscopy properties.

    This struct is mainly used to set up auto-saving spectroscopies.
    """

    save_all: int = base.SettingState.NO_CHANGE  # 2 bytes, unsigned int16
    number_of_sweeps: int = base.SettingState.NO_CHANGE  # 4 bytes, int32
    backward_sweep: int = base.SettingState.NO_CHANGE  # 2 bytes, unsigned int16
    number_of_points: int = base.SettingState.NO_CHANGE  # 4 bytes, int32
    z_offset_m: float = 0  # 4 bytes, float32
    auto_save: int  # 2 bytes, unsigned int16
    show_save_dialog: int  # 2 bytes, unsigned int16

    def format(self) -> str:
        """Override."""
        return 'HiHifHH'


# Pseudonyms for consistency
BiasSpectraPropsStruct = SpectraPropsStruct
ZSpectraPropsStruct = SpectraPropsStruct


class BiasSpectraPropsSet(base.NanonisMessage):
    """Bias spectroscopy properties set."""

    def get_command_name(self) -> str:
        """Override."""
        return 'BiasSpectr.PropsSet'


class BiasSpectraPropsSetReq(BiasSpectraPropsSet, BiasSpectraPropsStruct):
    """Bias spectroscopy properties set request."""


class BiasSpectraPropsSetRep(base.EmptyResponse, BiasSpectraPropsSet):
    """Bias spectroscopy properties set response."""


class ZSpectraPropsSet(base.NanonisMessage):
    """Z spectroscopy properties set."""

    def get_command_name(self) -> str:
        """Override."""
        return 'ZSpectr.PropsSet'


class ZSpectraPropsSetReq(ZSpectraPropsSet, ZSpectraPropsStruct):
    """Z spectroscopy properties set request."""


class ZSpectraPropsSetRep(base.EmptyResponse, ZSpectraPropsSet):
    """Z spectroscopy properties set response."""


class BiasSpectraPropsGet(base.NanonisMessage):
    """Bias spectroscopy properties get."""

    def get_command_name(self) -> str:
        """Override."""
        return 'BiasSpectr.PropsGet'


class BiasSpectraPropsGetReq(BiasSpectraPropsGet, base.EmptyResponse):
    """Bias spectroscopy properties get request."""


class BiasSpectraPropsGetRep(BiasSpectraPropsGet, BiasSpectraPropsStruct):
    """Bias spectroscopy properties set response."""


class ZSpectraPropsGet(base.NanonisMessage):
    """Z spectroscopy properties get."""

    def get_command_name(self) -> str:
        """Override."""
        return 'ZSpectr.PropsGet'


class ZSpectraPropsGetReq(ZSpectraPropsGet, base.EmptyResponse):
    """Z spectroscopy properties get request."""


class ZSpectraPropsGetRep(ZSpectraPropsGet, ZSpectraPropsStruct):
    """Z spectroscopy properties set response."""


class SpectroscopyMode(enum.Enum):
    """The spectroscopy mode used, Bias or Z."""

    BIAS = enum.auto()
    Z = enum.auto()
