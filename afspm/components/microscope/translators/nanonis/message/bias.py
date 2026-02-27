"""Bias message structures."""
import logging
from dataclasses import dataclass
from . import base


logger = logging.getLogger(__name__)


@dataclass
class BiasStruct(base.NanonisMessage):
    """Voltage Bias. Unit is in V."""

    value: float = base.DEF_FLT  # 4 bytes, float32

    def format(self) -> str:
        """Override."""
        return 'f'


@dataclass
class BiasSet(base.NanonisMessage):
    """Voltage Bias set."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'Bias.Set'


class BiasSetReq(base.NanonisRequest, BiasStruct, BiasSet):
    """Voltage Bias set request."""


class BiasSetRep(base.EmptyResponse, BiasSet):
    """Bias set response."""


class BiasGet(base.NanonisMessage):
    """Voltage Bias get."""

    @staticmethod
    def get_command_name() -> str:
        """Override."""
        return 'Bias.Get'


class BiasGetReq(base.EmptyRequest, BiasGet):
    """Voltage Bias getter request."""


class BiasGetRep(base.NanonisResponse, BiasStruct, BiasGet):
    """Voltage Bias getter response."""
