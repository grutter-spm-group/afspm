"""Holds Omicron SXM controller parameters (and other extra logic)."""

import logging

import enum
import math  # For isclose
from dataclasses import dataclass
from typing import Any

from ... import params
from . import sxm


logger = logging.getLogger(__name__)


class CallerType(str, enum.Enum):
    """The caller type, used to determine the get/set function name."""

    SCAN = 'SCAN'
    FEEDBACK = 'FEEDBACK'
    SPECTRA = 'SPECTRA'
    CHANNEL = 'CHANNEL'


class FeedbackMode(enum.Enum):
    """The feedback mode used, STM or AFM."""

    STM = enum.auto()
    AFM = enum.auto()


def get_getter_substr(caller: CallerType) -> str:
    """Get the setter substring for a given CallerType."""
    match caller:
        case CallerType.SCAN:
            return 'GetScanPara'
        case CallerType.FEEDBACK:
            return 'GetFeedPara'  # TODO: Validate!
        case CallerType.SPECTRA:
            return 'GetSpectPara'
        case CallerType.CHANNEL:
            return 'GetChannel'
        case _:
            raise ValueError(f'{caller} is an unsupported CallerType.')


def get_setter_substr(caller: CallerType) -> str:
    """Get the setter substring for a given CallerType."""
    match caller:
        case CallerType.SCAN:
            return 'ScanPara'
        case CallerType.FEEDBACK:
            return 'FeedPara'
        case CallerType.SPECTRA:
            return 'SpectPara'
        case CallerType.CHANNEL:
            return 'SetChannel'
        case _:
            raise ValueError(f'{caller} is an unsupported CallerType.')


@dataclass
class SXMParameterInfo(params.ParameterInfo):
    """Adds caller attribute to ParameterInfo.

    We need this in the case of SXM to know what method we are calling.

    In the SXM case, we have two new attributes:
    - caller: a CallerType indicates the method call (see
    get_getter_substr and get_setter_substr above).
    - caller_id: for this method call, our parameter has a given
    id, which may be a str or int.

    Rather than providing the uuid, this class creates the uuid in its
    __post_init__() method.

    We have modified the method overrides to clarify this.
    """

    uuid: tuple[CallerType, str | int]
    caller: CallerType
    caller_id: str | int

    def __post_init__(self):
        """Configure uuid."""
        self.configure_uuid()

    def configure_uuid(self):
        """Set up the uuid based on other attributes."""
        self.uuid = (self.caller, self.caller_id)


class SXMParameterHandler(params.ParameterHandler):
    """Implements SXM-specific getter/setter logic for parameter handling.

    Notes:
    - The probe position set() and get() calls are in different coordinate
    systems (see readme)! To be consistent, we store a correction ratio in
    _cs_correction_ratio.

    Attributes:
        client: DDE client used to communicate with SXM.
        mode: FeedbackMode we are to be running in.
        cs_correction_ratio: [x, y] indicating correction ratio between
            get probe position and set probe position. Needed to properly
            set.
    """

    DEFAULT_MODE = FeedbackMode.AFM
    DEFAULT_CS_CORRECTION_RATIO = [3.964, 3.704]

    def __init__(self, client: sxm.DDEClient, mode: FeedbackMode = DEFAULT_MODE,
                 cs_correction_ratio: list[int] = DEFAULT_CS_CORRECTION_RATIO,
                 **kwargs):
        """Override create_parameter_info for our special one.

        Args:
            client: DDE client used to communicate with SXM.
            mode: FeedbackMode we are to be running in. Defaults to
                DEFAULT_MODE.
        """
        self.client = client
        self.cs_correction_ratio = cs_correction_ratio
        kwargs['param_info_class'] = SXMParameterInfo
        super().__init__(**kwargs)

        # Asserting some parameters' units are the same. If they're not
        # we cannot predict what some of our calls will do!
        assert (self.get_unit(SXMParam.CENTER_Y) ==
                self.get_unit(params.MicroscopeParameter.SCAN_SIZE_Y))

        self.mode = mode
        self.switch_feedback_mode(mode)

    def get_param_spm(self, spm_uuid: tuple[CallerType, str | int]) -> Any:
        """Override for SPM-specific getter."""
        caller = spm_uuid[0]
        caller_id = spm_uuid[1]
        # Special case for CHANNEL get calls.
        # Get is negative, Set positive (for mysterious reasons).
        if caller == CallerType.CHANNEL:
            caller_id = -1 * caller_id

        caller_substr = get_getter_substr(caller)
        return self._call_get(caller_substr, caller_id)

    def _call_get(self, method: str, attr: str | int) -> Any:
        """Error handling around get call."""
        try:
            if isinstance(attr, str):
                attr = "'" + attr + "'"
            call_str = "a:=" + method + f"({attr});\r\nwriteln(a);"

            val = self.client.execute_and_return(call_str)
            if val is not None:
                return val
            else:
                msg = (f"Getting {attr} returned None. This happens when "
                       "the request sent to the SXM controller is not "
                       "recognized. Verify that the parameter requested is "
                       "spelled correctly and exists.")
                logger.error(msg)
                raise Exception(msg)

        except (sxm.RequestError, TimeoutError, sxm.SynchronizationError) as e:
            msg = f"Error getting parameter {attr}: {e}"
            raise params.ParameterError(msg)

    def set_param_spm(self, spm_uuid: tuple[CallerType, str | int]
                      , spm_val: Any):
        """Override for SPM-specific setter."""
        caller = spm_uuid[0]
        caller_id = spm_uuid[1]
        caller_substr = get_setter_substr(caller)
        self._call_set(caller_substr, caller_id, spm_val)

    def _call_set(self, substr: str, attr: str | int, val: str):
        """Error handling around set call."""
        try:
            if isinstance(attr, str):
                attr = "'" + attr + "'"
            self.client.execute_no_return(substr + f"({attr},{val});")
        except sxm.RequestError as e:
            msg = f"Error setting scan parameter {attr} to {val}: {e}"
            raise params.ParameterError(msg)

    def switch_feedback_mode(self, mode: FeedbackMode):
        """Switch to using the appropriate feedback mode."""
        ratio = 0 if mode == FeedbackMode.AFM else 100
        self.client.execute_no_return(f"FeedPara('Ratio', {ratio});")
        # Change Ki/Kp value for appropriate mode.
        gid = params.MicroscopeParameter.ZCTRL_PGAIN
        info = self._get_param_info(gid)
        info.caller_id = 'Kp' if mode == FeedbackMode.AFM else 'Kp2'
        info.configure_uuid()
        self.param_infos[gid] = info

        gid = params.MicroscopeParameter.ZCTRL_IGAIN
        info = self._get_param_info(gid)
        info.caller_id = 'Ki' if mode == FeedbackMode.AFM else 'Ki2'
        info.configure_uuid()
        self.param_infos[gid] = info

        self.mode = mode


class SXMParam(params.MicroscopeParameterBase):
    """SXM-specific parameters, used as 'generic' names in config.

    We use the 'name' of these parameters as their generic uuid when
    querying them from the params config. So, for example, for CENTER_X,
    we expect:
        [center-x]
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
    SCAN_AUTOSAVE = 'scan-autosave'

    # NOTE: These are set only
    SPEC_AUTOSAVE = 'spec-autosave'
    SPEC_REPEAT = 'spec-repeat'

    # --- The below are for dealing with probe position --- #
    # Position for running spec.
    SPEC_POS_X = 'spec-pos-x'  # Set only.
    SPEC_POS_Y = 'spec-pos-y'  # Set only.
    # Actual position of probe.
    TIP_POS_X = 'tip-pos-x'  # Get only.
    TIP_POS_Y = 'tip-pos-y'  # Get only.

    # --- Spectroscopy settings --- #
    # NOTE: These are set only
    SPEC_MODE = 'spec-mode'
    DZ_U_DELAY = 'dz-u-delay'  # ms
    DZ_U_ACQUISITION_TIME = 'dz-u-acq-t'  # ms
    DZ_U_DZ1 = 'dz-u-dz1'  # nm

    DZ_DZ2 = 'dz-dz2'  # nm

    U_U_START = 'u-u-start'  # mV
    U_U_STOP = 'u-u-stop'  # mV


# ---- Special Conversions ----- #
# Special conversions due to differences between SXM and our generic model.
# Note that we do not do unit conversions for data within params.toml here;
# rather, we check at __init__ of the ParameterHandler.


# ----- Top-Left Position Methods ----- #
def center_to_top_left(pos: float, size: float):
    """Go from center -> TL."""
    return pos - 0.5*size


def top_left_to_center(pos: float, size: float):
    """Go from center -> TL."""
    return pos + 0.5*size


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

    if math.isclose(size_y, 0.0):  # TODO: consider rel_tol?
        msg = 'Cannot set scan-size-x due to scan-size-y being 0.'
        raise params.ParameterError(msg)

    # Ensure within expected ranges!
    gid = params.MicroscopeParameter.SCAN_SIZE_X
    val = params._correct_val_for_sending(
        val, handler._get_param_info(gid), unit, gid)

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

    if res_y == 0:
        msg = 'Cannot set scan-resolution-x due to scan-resolution-y being 0.'
        raise params.ParameterError(msg)

    # Ensure within expected ranges!
    gid = params.MicroscopeParameter.SCAN_RESOLUTION_X
    val = params._correct_val_for_sending(
        val, handler._get_param_info(gid), unit, gid)

    val = val / res_y
    handler.set_param(SXMParam.PIXEL_X_RATIO, val)


# Hard-coded allowed resolutions for setting.
ALLOWED_RESOLUTIONS = [32, 64, 128, 256, 512]


def set_res_y(handler: params.ParameterHandler,
              val: Any, unit: str):
    """Set scan resolution y-dim.

    The API only seems to allow one of ALLOWED_RESOLUTIONS to be set.
    Here, we set to the closest resolution and provide a warning if the
    fed val is not one of these.
    """
    diff = [abs(allowed_res - val) for allowed_res in ALLOWED_RESOLUTIONS]
    index = diff.index(min(diff))

    if diff[index] != 0:
        msg = (f'Fed scan-resolution-y {val} is not one of allowed. '
               'Please set a supported resolution from '
               f'{ALLOWED_RESOLUTIONS}.')
        raise params.ParameterError(msg)

    # Strangely, we set the *index* of the allowed resolutions to set,
    # but get the actual resolution...
    handler.set_param(params.MicroscopeParameter.SCAN_RESOLUTION_Y,
                      index, unit, override_methods=True)


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
    lines_s = handler.get_param(SXMParam.SPEED_LINES_S)
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
    val = params._correct_val_for_sending(
        val, handler._get_param_info(gid), unit, gid)

    size_uuid = params.MicroscopeParameter.SCAN_SIZE_X
    size_x = handler.get_param(size_uuid)
    val = speed_metric_s_to_lines_s(val, size_x)
    handler.set_param(SXMParam.SPEED_LINES_S, val)


# ----- Probe Position Methods ----- #
def get_to_set_cs(val: float, offset: float, correction_ratio: float) -> float:
    """Correct from the get CS to set CS."""
    return val + offset / correction_ratio


def set_to_get_cs(val: float, offset: float, correction_ratio: float) -> float:
    """Correct from the set to get CS."""
    return val - offset / correction_ratio


def get_probe_pos_x(handler: params.ParameterHandler) -> Any:
    """Get Probe Position (X-).

    The interface for accessing this is non-standard, this is why
    the custom functions are needed.

    Of note: we get via TIP_POS_X and set via SPEC_POS_X.
    """
    return handler.get_param(SXMParam.TIP_POS_X)


def get_probe_pos_y(handler: params.ParameterHandler) -> Any:
    """Get Probe Position (Y-).

    The interface for accessing this is non-standard, this is why
    the custom functions are needed.

    Of note: we get via TIP_POS_Y and set via SPEC_POS_Y.
    """
    return handler.get_param(SXMParam.TIP_POS_Y)


def set_probe_pos_x(handler: params.ParameterHandler,
                    val: Any, unit: str):
    """Set Probe Position (X-).

    The interface for accessing this is non-standard, this is why
    the custom functions are needed.

    Of note: we get via TIP_POS_X and set via SPEC_POS_X.
    """
    offset_uuid = SXMParam.CENTER_X
    offset = handler.get_param(offset_uuid)

    gid = params.MicroscopeParameter.PROBE_POS_X
    val = params._correct_val_for_sending(
        val, handler._get_param_info(gid), unit, gid)

    # Convert to 'set' CS.
    val = get_to_set_cs(val, offset, handler.cs_correction_ratio[0])
    handler.set_param(SXMParam.SPEC_POS_X, val, unit)


def set_probe_pos_y(handler: params.ParameterHandler,
                    val: Any, unit: str):
    """Set Probe Position (Y-).

    The interface for accessing this is non-standard, this is why
    the custom functions are needed.

    Of note: we get via TIP_POS_Y and set via SPEC_POS_Y.
    """
    offset_uuid = SXMParam.CENTER_Y
    offset = handler.get_param(offset_uuid)

    gid = params.MicroscopeParameter.PROBE_POS_Y
    val = params._correct_val_for_sending(
        val, handler._get_param_info(gid), unit, gid)

    # Convert to 'set' CS.
    val = get_to_set_cs(val, offset, handler.cs_correction_ratio[1])
    handler.set_param(SXMParam.SPEC_POS_Y, val, unit)


class SpectroscopyMode(enum.Enum):
    """Supported spectroscopy modes."""

    # The enum values match the SXM interface setting value.
    X_Z = 0  # X(z) (Height)
    X_U = enum.auto()  # X(U) (Bias)
    X_U_CL = enum.auto()  # X(U) CL
    X_T_Z_STEP = enum.auto()  # X(t) z-step
    X_T_Z_STEP_CL = enum.auto()  # X(t) z-step CL
    X_T_U_STEP = enum.auto()  # X(t) U-step
    X_T_U_STEP_CL = enum.auto()  # X(t) U-step CL
    CM_AFM_X_U = enum.auto()  # cmAFM X(U)
    X_T_NOISE = enum.auto()  # X(t) noise
    X_X_Y = enum.auto()  # X(x, y)


@dataclass
class SpectroscopySettingsHeight():
    """Settings for D(z) spectroscopies."""

    delay_s: float
    acquisition_time_s: float
    dz1_nm: float
    dz2_nm: float

    @classmethod
    def get_uuids(cls) -> list[SXMParam]:
        """Return uuids as a list."""
        return [SXMParam.DZ_U_DELAY,
                SXMParam.DZ_U_ACQUISITION_TIME,
                SXMParam.DZ_U_DZ1,
                SXMParam.DZ_DZ2]


@dataclass
class SpectroscopySettingsBias():
    """Settings for D(U) spectroscopies."""

    delay_s: float
    acquisition_time_s: float
    dz_nm: float
    bias_start: float
    bias_stop: float

    @classmethod
    def get_uuids(cls) -> list[SXMParam]:
        """Return uuids as a list."""
        return [SXMParam.DZ_U_DELAY,
                SXMParam.DZ_U_ACQUISITION_TIME,
                SXMParam.DZ_U_DZ1,
                SXMParam.U_U_START,
                SXMParam.U_U_STOP]
