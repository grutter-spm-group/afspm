"""Spectroscopy message structures."""
import logging
from dataclasses import dataclass
import enum
from . import base


logger = logging.getLogger(__name__)


# ----- Spectra Start ----- #
@dataclass
class SpectraStart(base.NanonisMessage):
    """Spectroscopy start.

    NOTE:
    - The channels to record must be set via the UI before using!
    - By default, get_data is 0 so we do not request the data.
    - By default, base_name is '', so we do not change the base name.
    """

    get_data: bool = base.DEF_INT  # 4 bytes, unsigned int32  (default False)
    name_size: int = base.DEF_INT  # 4 bytes, int32
    base_name: str = base.DEF_STR  # Size defined by name_size

    def format(self) -> str:
        """Override."""
        return 'Ii%ds' % (len(self.name_size),)


class SpectraStartReq(base.NanonisRequest, SpectraStart):
    """Spectroscopy start request."""

    @staticmethod
    def request_response() -> bool:
        """Not requesting response, in hopes we get asynchronous.

        The documentation implies that the full spectroscopy is returned,
        meaning it would need to be synchronous. We are hoping that, in
        *not* requesting a response, we get a quick asynchronous return.
        """
        return False


class BiasSpectraStart(SpectraStart):
    """Bias spectroscopy start."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'BiasSpectr.Start'


class BiasSpectraStartReq(BiasSpectraStart, SpectraStartReq):
    """Bias spectroscopy start request."""


class BiasSpectraStartRep(base.EmptyResponse, BiasSpectraStart):
    """Bias spectroscopy start request."""


class ZSpectraStart(SpectraStart):
    """Z spectroscopy start."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'ZSpectr.Start'


class ZSpectraStartReq(ZSpectraStart, SpectraStartReq):
    """Z spectroscopy start request."""


class ZSpectraStartRep(base.EmptyResponse, ZSpectraStart):
    """Z spectroscopy start request."""


# ----- Spectra Stop ----- #
class BiasSpectraStop(base.NanonisMessage):
    """Bias spectroscopy stop."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'BiasSpectr.Stop'


class BiasSpectraStopReq(base.EmptyRequest, BiasSpectraStop):
    """Bias spectroscopy stop request."""


class BiasSpectraStopRep(base.EmptyResponse, BiasSpectraStop):
    """Bias spectroscopy stop response."""


class ZSpectraStop(base.NanonisMessage):
    """Z spectroscopy stop."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'ZSpectr.Stop'


class ZSpectraStopReq(base.EmptyRequest, ZSpectraStop):
    """Z spectroscopy stop request."""


class ZSpectraStopRep(base.EmptyResponse, ZSpectraStop):
    """Z spectroscopy stop response."""


# ----- Spectra Status ----- #
@dataclass
class SpectraStatusStruct(base.NanonisMessage):
    """Spectroscopy status.

    NOTE:
    - Default status to non-sensical value to ensure parsing properly.
    """

    status: int = -1  # 4 bytes, unsigned int32

    def format(self) -> str:
        """Override."""
        return 'I'


class BiasSpectraStatusGet(base.NanonisMessage):
    """Bias spectroscopy status."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'BiasSpectr.StatusGet'


class ZSpectraStatusGet(base.NanonisMessage):
    """Z spectroscopy status."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'ZSpectr.StatusGet'


# Pseudonyms for consistency
BiasSpectraStatusStruct = SpectraStatusStruct
ZSpectraStatusStruct = SpectraStatusStruct


class BiasSpectraStatusGetReq(base.EmptyRequest, BiasSpectraStatusGet):
    """Bias spectroscopy status request."""


class BiasSpectraStatusGetRep(base.NanonisResponse, BiasSpectraStatusGet,
                              BiasSpectraStatusStruct):
    """Bias spectroscopy status request."""


class ZSpectraStatusGetReq(base.EmptyRequest, ZSpectraStatusGet):
    """Z spectroscopy status request."""


class ZSpectraStatusGetRep(base.NanonisResponse, ZSpectraStatusGet,
                           ZSpectraStatusStruct):
    """Z spectroscopy status request."""


@dataclass
class BiasSpectraPropsSetStruct(base.NanonisMessage):
    """Bias Spectroscopy properties.

    This struct is mainly used to set up auto-saving spectroscopies.

    NOTE:
    - By default, z_offset_m is 0 to not change the z-position.
    """

    save_all: int = base.NO_CHANGE_VAL  # 2 bytes, unsigned int16
    number_of_sweeps: int = base.NO_CHANGE_VAL  # 4 bytes, int32
    backward_sweep: int = base.NO_CHANGE_VAL  # 2 bytes, unsigned int16
    number_of_points: int = base.NO_CHANGE_VAL  # 4 bytes, int32
    z_offset_m: float = base.DEF_FLT  # 4 bytes, float32
    auto_save: int = base.NO_CHANGE_VAL  # 2 bytes, unsigned int16
    show_save_dialog: int = base.NO_CHANGE_VAL  # 2 bytes, unsigned int16

    def format(self) -> str:
        """Override."""
        return 'HiHifHH'


class BiasSpectraPropsSet(base.NanonisMessage):
    """Bias spectroscopy properties set."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'BiasSpectr.PropsSet'


class BiasSpectraPropsSetReq(base.NanonisRequest, BiasSpectraPropsSet,
                             BiasSpectraPropsSetStruct):
    """Bias spectroscopy properties set request."""


class BiasSpectraPropsSetRep(base.EmptyResponse, BiasSpectraPropsSet):
    """Bias spectroscopy properties set response."""


@dataclass
class ZSpectraPropsSetStruct(base.NanonisMessage):
    """Z Spectroscopy properties.

    This struct is mainly used to set up auto-saving spectroscopies.
    """

    backward_sweep: int = base.NO_CHANGE_VAL  # 2 bytes, unsigned int16
    number_of_points: int = base.NO_CHANGE_VAL  # 4 byts, int32
    # NOTE: number_of_sweeps for ZSpectra diff from bias spectra...
    number_of_sweeps: int = base.NO_CHANGE_VAL  # 2 bytes, unsigned int16
    auto_save: int = base.NO_CHANGE_VAL  # 2 bytes, unsigned int16
    show_save_dialog: int = base.NO_CHANGE_VAL  # 2 byts, unsigned int16
    save_all: int = base.NO_CHANGE_VAL  # 2 bytse, unsigned int16

    def format(self) -> str:
        """Override."""
        return 'HiHHHH'


class ZSpectraPropsSet(base.NanonisMessage):
    """Z spectroscopy properties set."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'ZSpectr.PropsSet'


class ZSpectraPropsSetReq(base.NanonisRequest, ZSpectraPropsSet,
                          ZSpectraPropsSetStruct):
    """Z spectroscopy properties set request."""


class ZSpectraPropsSetRep(base.EmptyResponse, ZSpectraPropsSet):
    """Z spectroscopy properties set response."""


class SpectroscopyMode(enum.Enum):
    """The spectroscopy mode used, Bias or Z."""

    BIAS = enum.auto()
    Z = enum.auto()
