"""Holds Omicron SXM controller parameters (and other extra logic)."""

import logging

import enum
from dataclasses import dataclass
from typing import Any, Callable

from afspm.components.microscope import params

from SXMRemote import DDEClient


logger = logging.getLogger(__name__)


class CallerType(str, enum.Enum):
    """The caller type, used to determine the get/set function name."""

    SCAN = 'SCAN'
    FEEDBACK = 'FEEDBACK'
    SPECTRA = 'SPECTRA'


class FeedbackMode(enum.Enum):
    """The feedback mode used, STM or AFM."""

    STM = enum.auto()
    AFM = enum.auto()


def get_getter_callable(client: DDEClient, caller: CallerType) -> Callable:
    """Get the getter callable for a given CallerType."""
    match caller:
        case CallerType.SCAN:
            return client.GetScanPara
        case CallerType.FEEDBACK:
            return client.GetFeedbackPara
        case CallerType.SPECTRA:
            return client.GetSpectPara
        case _:
            return None


def get_setter_substr(caller: CallerType) -> str:
    """Get the setter substring for a given CallerType."""
    match caller:
        case CallerType.SCAN:
            return 'GetScanPara'
        case CallerType.FEEDBACK:
            return 'GetFeedbackPara'  # TODO: Validate!
        case CallerType.SPECTRA:
            return 'GetSpectPara'
        case _:
            return None


@dataclass
class SXMParameterInfo(params.ParameterInfo):
    """Adds param caller TODO Finish."""

    caller: CallerType  # Indicates 'grouping' this param is in.


def create_param_info(param_dict: dict) -> SXMParameterInfo:
    """Like params.create_parameter_info, but for SXM ParameterInfo."""
    vals = []
    for key in SXMParameterInfo.__annotations__.keys():
        vals.append(param_dict[key] if key in param_dict else None)
    return SXMParameterInfo(*vals)


class SXMParameterHandler(params.ParameterHandler):
    """Implements SXM-specific getter/setter logic for parameter handling.

    Attributes:
        client: DDE client used to communicate with SXM.
        param_caller: holds the CallerType of the latest parameter we
            wish to access. It is set in get_param()/set_param(), and
            used by get_param_spm()/set_param_spm().
        mode: FeedbackMode we are to be running in.
    """

    def __init__(self, client: DDEClient, mode: FeedbackMode, **kwargs):
        """Override create_parameter_info for our special one.

        Args:
            client: DDE client used to communicate with SXM.
            mode: FeedbackMode we are to be running in.
        """
        self.client = client
        self.param_caller = None
        kwargs['param_info_init'] = create_param_info
        self.__init__(**kwargs)

        # Asserting some parameters' units are the same. If they're not
        # we cannot predict what some of our calls will do!
        assert (self.get_unit(params.MicroscopeParameter.SCAN_TOP_LEFT_X) ==
                self.get_unit(params.MicroscopeParameter.SCAN_SIZE_X))
        assert (self.get_unit(params.MicroscopeParameter.SCAN_TOP_LEFT_Y) ==
                self.get_unit(params.MicroscopeParameter.SCAN_SIZE_Y))

        self.mode = mode
        self._switch_feedback_mode(mode)

    def get_param(self, generic_param: params.MicroscopeParameter) -> Any:
        """Override to store get-set substr."""
        self.param_caller = self._get_param_info(generic_param).caller
        val = super().get_param(generic_param)
        self.param_caller = None
        return val

    def get_param_spm(self, spm_uuid: str) -> Any:
        """Override for SPM-specific getter."""
        method = get_getter_callable(self.client, self.param_caller)
        return self._call_get(method, spm_uuid)

    def _call_get(self, method: Callable, attr: str) -> Any:
        """Error handling around get call."""
        try:
            val = method(f"\'{attr}\'")
            if val is not None:
                return val
            else:
                # TODO make nice string here
                msg = (f"Getting {attr} returned None. This happens when "
                       "the request sent to the SXM controller is not "
                       "recognized. Verify that the parameter requested is "
                       "spelled correctly and exists.")
                logger.error(msg)
                raise Exception(msg)

        except Exception as e:
            # Or should I simply allow the code to crash if there's an error in
            # Anfatec's code? TODO
            msg = f"Error in SXM's Python interface while getting {attr}: {e}"
            logger.error(msg)
            raise Exception(msg)

    def set_param(self, generic_param: params.MicroscopeParameter, val: Any,
                  curr_unit: str = None):
        """Override to store get-set method."""
        self.param_caller = self._get_param_info(generic_param).caller
        super().set_param(generic_param, val, curr_unit)
        self.param_caller = None

    def set_param_spm(self, spm_uuid: str, spm_val: Any):
        """Override for SPM-specific setter."""
        substr = get_setter_substr(self.param_caller)
        self._call_set(substr, spm_uuid, spm_val)

    def _call_set(self, substr: str, attr: str, val: str):
        """Error handling around set call."""
        try:
            self.client.SendWait(substr + f"('{attr}',{val});")
        except Exception as e:
            msg = f"Error setting scan parameter {attr} to {val}: {e}"
            logger.error(msg)
            raise params.ParameterError(msg)

    def _switch_feedback_mode(self, mode: FeedbackMode):
        """Switch to using the appropriate feedback mode."""
        ratio = 0 if mode == FeedbackMode.AFM else 100
        self.client.SendWait(f"SendFeedPara('Ratio', {ratio})")
        # Change Ki/Kp value for appropriate mode.
        gid = params.MicroscopeParameter.ZCTRL_PGAIN
        info = self._get_param_info(gid)
        info.uuid = 'Kp' if mode == FeedbackMode.AFM else 'Kp2'
        self.param_infos[gid] = info

        gid = params.MicroscopeParameter.ZCTRL_IGAIN
        info = self._get_param_info(gid)
        info.uuid = 'Ki' if mode == FeedbackMode.AFM else 'Ki2'
        self.param_infos[gid] = info

        self.mode = mode


class SXMParam(params.MicroscopeParameter):
    """SXM-specific parameters, used as 'generic' names in config.

    We use the 'name' of these parameters as their generic uuid when
    querying them from the params config. So, for example, for CENTER_X,
    we expect:
        [CENTER_X]
        uuid = 'something'
        [...]
    In the config file.

    Note that the caller is crucial, as that allows us to know how to call
    the appropriate get/set method.
    """

    CENTER_X = 'center-x'
    CENTER_Y = 'center-y'
    SIZE_X_RATIO = 'size-x-ratio'
    PIXEL_X_RATIO = 'pixel-x-ratio'
    SPEED_LINES_S = 'speed-lines-s'
    SCAN_STATE = 'scan-state'
    SPEC_AUTOSAVE = 'spec-autosave'
    SPEC_REPEAT = 'spec-repeat'


# ---- Special Conversions ----- #
# Special conversions due to differences between SXM and our generic model.
# Note that we do not do unit conversions for data within params.toml here;
# rather, we check at __init__ of the ParameterHandler.


# ----- Top-Left Position Methods ----- #
def center_to_top_left(pos: float, size: float):
    """Go from center -> TL."""
    return pos + 0.5*size


def top_left_to_center(pos: float, size: float):
    """Go from center -> TL."""
    return pos - 0.5*size


def get_scan_x(handler: params.ParameterHandler) -> Any:
    """Get top-left x-position of scan.

    The SXM stores the center position, so we need to add half of
    (width/height) to what we receive.
    """
    generic_ids = [SXMParam.CENTER_X,
                   params.MicroscopeParameter.SCAN_SIZE_X]
    vals = handler.get_param_list(generic_ids)
    return center_to_top_left(vals[0], vals[1])


def get_scan_y(handler: params.ParameterHandler) -> Any:
    """Get top-left y-position of scan.

    The SXM stores the center position, so we need to add half of
    (width/height) to what we receive.
    """
    generic_ids = [SXMParam.CENTER_Y,
                   params.MicroscopeParameter.SCAN_SIZE_Y]
    vals = handler.get_param_list(generic_ids)
    return center_to_top_left(vals[0], vals[1])


def set_scan_x(handler: params.ParameterHandler,
               val: Any, unit: str):
    """Set top-left x-position of scan.

    The SXM stores the center position, so we need to subtract half of
    (width/height) to what we receive.
    """
    size = handler.get_param(params.MicroscopeParameter.SCAN_SIZE_X)
    pos = top_left_to_center(val, size)
    handler.set_param(SXMParam.CENTER_X, pos, unit)


def set_scan_y(handler: params.ParameterHandler,
               val: Any, unit: str):
    """Set top-left y-position of scan.

    The SXM stores the center position, so we need to subtract half of
    (width/height) to what we receive.
    """
    size = handler.get_param(params.MicroscopeParameter.SCAN_SIZE_Y)
    pos = top_left_to_center(val, size)
    handler.set_param(SXMParam.CENTER_Y, pos, unit)


# ----- Size / Resolution Methods ----- #
def get_size_x(handler: params.ParameterHandler) -> Any:
    """Get the size of the X-dimension.

    In SXM, the Y-dimension is stored and an aspect ratio is stored to
    convert this to the X-dimension. Thus, we do this operation here.
    """
    generic_ids = [SXMParam.SIZE_X_RATIO,
                   params.MicroscopeParameter.SCAN_SIZE_Y]
    vals = handler.get_param_list(generic_ids)
    return vals[0] * vals[1]


def get_res_x(handler: params.ParameterHandler) -> Any:
    """Get the resolution of the X-dimension.

    In SXM, the Y-dimension is stored and an aspect ratio is stored to
    convert this to the X-dimension. Thus, we do this operation here.
    """
    generic_ids = [SXMParam.PIXEL_X_RATIO,
                   params.MicroscopeParameter.SCAN_RESOLUTION_Y]
    vals = handler.get_param_list(generic_ids)
    return vals[0] * vals[1]


def set_size_x(handler: params.ParameterHandler,
               val: Any, unit: str):
    """Set the size of the X-dimension.

    In SXM, the Y-dimension is stored and an aspect ratio is stored to
    convert this to the X-dimension. Thus, we do this operation here.

    NOTE: We are manually using _correct_val_for_sending() here, because
    the stored data is an aspect ratio and thus the range checking
    is less clear. Thus, we ensure it is within SCAN_SIZE_X ranges
    before converting to a ratio.
    """
    size_y = handler.get_param(params.MicroscopeParameter.SCAN_SIZE_Y)

    # Ensure within expected ranges!
    gid = params.MicroscopeParameter.SCAN_SIZE_X
    val = handler._correct_val_for_sending(
        val, handler.get_param_info(gid), unit, gid)

    val = val / size_y
    handler.set_param(SXMParam.SIZE_X_RATIO, val)


def set_res_x(handler: params.ParameterHandler,
              val: Any, unit: str):
    """Set the resolution of the X-dimension.

    In SXM, the Y-dimension is stored and an aspect ratio is stored to
    convert this to the X-dimension. Thus, we do this operation here.

    NOTE: We are manually using _correct_val_for_sending() here, because
    the stored data is an aspect ratio and thus the range checking
    is less clear. Thus, we ensure it is within SCAN_RESOLUTION_X ranges
    before converting to a ratio.
    """
    res_y = handler.get_param(params.MicroscopeParameter.SCAN_RESOLUTION_Y)

    # Ensure within expected ranges!
    gid = params.MicroscopeParameter.SCAN_RESOLUTION_X
    val = handler._correct_val_for_sending(
        val, handler.get_param_info(gid), unit, gid)

    val = val / res_y
    handler.set_param(SXMParam.PIXEL_X_RATIO, val)


# ----- Scan Speed Methods ----- #
def speed_lines_s_to_metric_s(lines_s: float, scan_width_metric: float):
    """Go from lines/s to metric/s."""
    return lines_s * scan_width_metric


def speed_metric_s_to_lines_s(metric_s: float, scan_width_metric: float):
    """Go from metric/s to lines/s ."""
    return metric_s / scan_width_metric


def get_scan_speed(handler: params.ParameterHandler) -> Any:
    """Get scan speed in metric units / s.

    The scan speed is stored in SXM in lines / s, i.e. Hz. To convert,
    we need to consider the scan width.
    """
    size_x = handler.get_param(params.MicroscopeParameter.SCAN_SIZE_X)
    lines_s = params.get_param(SXMParam.SPEED_LINES_S)
    return speed_lines_s_to_metric_s(lines_s, size_x)


def set_scan_speed(handler: params.ParameterHandler,
                   val: Any, unit: str):
    """Set the scan speed.

    The scan speed is stored in SXM in lines / s, i.e. Hz. To convert,
    we need to consider the scan width.

    NOTE: We are manually using _correct_val_for_sending() here, because
    the stored data is in lines/s and thus the range checking
    is less clear. Thus, we ensure it is within SCAN_SPEED ranges
    before converting to a ratio.
    """
    # Ensure within expected ranges!
    gid = params.MicroscopeParameter.SCAN_SPEED
    val = handler._correct_val_for_sending(
        val, handler.get_param_info(gid), unit, gid)

    size_uuid = params.MicroscopeParameter.SCAN_SIZE_X
    size_x = handler.get_param(size_uuid)
    val = speed_metric_s_to_lines_s(val, size_x)
    handler.set_param(SXMParam.SPEED_LINES_S)


# ----- Probe Position Methods ----- #
PROBE_POS_X_GET_ID = -2
PROBE_POS_Y_GET_ID = -3
PROBE_POS_X_SET_ID = 1
PROBE_POS_Y_SET_ID = 2


def get_probe_pos_x(handler: params.ParameterHandler) -> Any:
    """Get Probe Position (X-).

    The interface for accessing this is non-standard, this is why
    the custom functions are needed.
    """
    return handler._call_get(handler.client.GetChannel,
                             PROBE_POS_X_GET_ID)


def get_probe_pos_y(handler: params.ParameterHandler) -> Any:
    """Get Probe Position (Y-).

    The interface for accessing this is non-standard, this is why
    the custom functions are needed.
    """
    return handler._call_get(handler.client.GetChannel,
                             PROBE_POS_Y_GET_ID)


def set_probe_pos_x(handler: params.ParameterHandler,
                    val: Any, unit: str):
    """Set Probe Position (X-).

    The interface for accessing this is non-standard, this is why
    the custom functions are needed.
    """
    gid = params.MicroscopeParameter.PROBE_POS_X
    val = handler._correct_val_for_sending(
        val, handler.get_param_info(gid), unit, gid)

    handler._call_set(get_setter_substr(CallerType.SPECTRA),
                      PROBE_POS_X_SET_ID, val)


def set_probe_pos_y(handler: params.ParameterHandler,
                    val: Any, unit: str):
    """Set Probe Position (Y-).

    The interface for accessing this is non-standard, this is why
    the custom functions are needed.
    """
    gid = params.MicroscopeParameter.PROBE_POS_Y
    val = handler._correct_val_for_sending(
        val, handler.get_param_info(gid), unit, gid)

    handler._call_set(get_setter_substr(CallerType.SPECTRA),
                      PROBE_POS_Y_SET_ID, val)
