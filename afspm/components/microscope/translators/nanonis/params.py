"""Holds Nanonis controller parameters (and other extra logic)."""

import logging
import enum
from dataclasses import dataclass
from typing import Any, Callable

from ... import params
#from .message.spectroscopy import   # Import using parser instead?
from .client import NanonisClient


logger = logging.getLogger(__name__)


class SpectroscopyMode(enum.Enum):
    """The spectroscopy mode used, Bias or Z."""

    BIAS = enum.auto()
    Z = enum.auto()


@dataclass
class NanonisParameterInfo(params.ParameterInfo):
    """Expanding ParameterInfo to be used for Nanonis params.

    Here, we are adding an attribute and modifying one for our needs.

    uuid (modified):
    ----

    this now refers to the 'prefix' for the various NanonisMessages
    associated to this call. Each API call is linked to:
    - A VARIABLEStruct NanonisMessage, which is a dataclass containing
    the structure of the buffer we will send/receive.
    - A VARIABLESet NanonisMessage, which contains the setter command
    name.
    - A VARIABLEGet NanonisMessage, which contains the getter command
    name.
    - VARIABLESetReq / VARIABLESetRep and VARIABLEGetReq / VARIABLEGetRep
    messages, which inherit from the appropriate about messages. For
    example, to set the voltage bias, BiasSetReq inherits from
    BiasStruct, while BiasSetRep inehrits from EmptyResponse.

    Here, VARIABLE is the 'prefix'. So, we indicate which NanonisMessages
    to use for a given call by setting uuid to VARIABLE. Note that these
    will be imported in the same way as the getter/setter, so you should
    include the full path to it.

    index (added):
    -----

    This is an added parameter. It is to hold the index of the VARIABLEStruct
    associated to this particular parameter. The reason is that Nanonis
    bundles various parameters into composite ones, so a given generic
    parameter may only be accessible by querying the composite parameter
    and extracting the individual parameter of interest (via its index).

    If the generic parameter maps to an individual parameter (i.e. not
    a composite), you can likely set index to 0. This is best determined
    by reviewing the associated NanonisMessage.
    """

    index: int  # Indicates VARIABLEStruct index for this parameter.


def create_param_info(param_dict: dict) -> NanonisParameterInfo:
    """Like params.create_parameter_info, but for NanonisParameterInfo."""
    vals = []
    for key in NanonisParameterInfo.__annotations__.keys():
        vals.append(param_dict[key] if key in param_dict else None)
    return NanonisParameterInfo(*vals)


class NanonisParameterHandler(params.ParameterHandler):
    """Implements Nanonis-specific logic for parameter handling.

    Attributes:
        _client: TCP client usd to communicate with Nanonis.
        _mode: SpectroscopyMode we are to be running in.
    """

    DEFAULT_MODE = SpectroscopyMode.Bias

    def __init__(self, client: NanonisClient,
                 mode: SpectroscopyMode = DEFAULT_MODE,
                 **kwargs):
        """Override create_parameter_info for our special one.

        Args:
            client: TCP client used to communicate with Nanonis.
            mode: SpectroscopyMode we are to be running in. Defaults to
                DEFAULT_MODE.
        """
        self._client = client

        kwargs['param_info_init'] = create_param_info
        self.__init__(**kwargs)

        self._mode = mode
        self._switch_spectroscopy_mode(mode)

    def _switch_spectroscopy_mode(mode):
        """Switch to using the appropriate spectroscopy mode."""
        # TODO: Change the appropriate uuids in the TOML!
