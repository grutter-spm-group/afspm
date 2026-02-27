"""Handles device communication with the Nanonis controller."""

import os.path
import glob
import logging

import SciFiReaders as sr

from ...translator import FLOAT_TOLERANCE_KEY
from ...params import (ParameterHandler, DEFAULT_PARAMS_FILENAME,
                       MicroscopeParameter)
from ...actions import (ActionHandler, DEFAULT_ACTIONS_FILENAME)
from ...import config_translator as ct
from .....utils import array_converters as conv

from .....io.protos.generated import scan_pb2
from .....io.protos.generated import spec_pb2
from .....io.protos.generated import control_pb2

from . import params
from . import actions
from .client import NanonisClient
from .message import base, spectroscopy


logger = logging.getLogger(__name__)


# Nanonis tolerance
FLOAT_TOLERANCE = 1e-07


class NanonisTranslator(ct.ConfigTranslator):
    """Handles device communication with the Nanonis controller.

    NOTE:
    - Although we store the old SetupProperties, we are not reverting to
    them on closure. Consider doing so!
    - The API accepts multiples of 16 for its x-dim resolution parameter.
    Keep this in mind.


    Attributes:
        _mode: SpectroscopyMode we are to be running in.

        _old_scans: the last scans, to send out if it has not changed.
        _old_scan_path: the prior scan filepath. We use this to avoid loading
            the same scans multiple times.
        _old_spec: the last spec, to send out if it has not changed.
        _old_spec_path: the prior spec filepath. We use this to avoid loading
            the same spectroscopies multiple times.
    """

    DEFAULT_MODE = spectroscopy.SpectroscopyMode.BIAS
    DESIRED_SETUP_PROPERTIES = params.SetupProperties(
        scan_auto_save=base.SettingState.ON.value,
        scan_continuous_scan=base.SettingState.OFF.value,
        spec_auto_save=base.SettingState.ON.value,
        spec_save_dialog=base.SettingState.OFF.value)

    SCAN_EXT = '.sxm'
    SPEC_EXT = '.dat'

    def __init__(self,
                 param_handler: ParameterHandler | None = None,
                 action_handler: ActionHandler | None = None,
                 client: NanonisClient | None = None,
                 mode: spectroscopy.SpectroscopyMode = DEFAULT_MODE,
                 **kwargs):
        """Construct translator."""
        self._mode = None
        self._old_scan_path = None
        self._old_scans = []
        self._old_spec_path = None
        self._old_spec = None

        # Default initialization of handler
        kwargs = self._init_handlers(client, param_handler, action_handler,
                                     **kwargs)

        # Tell parent class that Nanonis *does not* detect moving
        kwargs[ct.DETECTS_MOVING_KEY] = False
        # Set hard-coded float tolerance if not provided
        if FLOAT_TOLERANCE_KEY not in kwargs:
            kwargs[FLOAT_TOLERANCE_KEY] = FLOAT_TOLERANCE
        super().__init__(**kwargs)

        # Store current setup properties and set to our desired ones.
        self.set_setup_properties(self.DESIRED_SETUP_PROPERTIES)
        self.set_spectroscopy_mode(mode)

    def _init_handlers(self, client: NanonisClient,
                       param_handler: ParameterHandler,
                       action_handler: ActionHandler,
                       **kwargs) -> dict:
        """Init handlers and update kwargs."""
        if not client:
            client = NanonisClient()
        if not param_handler:
            param_handler = _init_param_handler(client)
            kwargs[ct.PARAM_HANDLER_KEY] = param_handler
        if not action_handler:
            action_handler = _init_action_handler(client)
            kwargs[ct.ACTION_HANDLER_KEY] = action_handler
        return kwargs

    def set_spectroscopy_mode(self, mode: spectroscopy.SpectroscopyMode):
        """Set spectroscopy mode."""
        self._mode = mode
        self.action_handler.set_spectroscopy_mode(self._mode)

    def _get_latest_file(self, ext: str) -> str | None:
        file_path = self.param_handler.get_param(params.NanonisParam.FILE_PATH)
        file_form = "*" + ext
        images = sorted(glob.glob(os.path.join(file_path, file_form)),
                        key=os.path.getmtime)  # Sorted by access time
        return images[-1] if images else None  # Get latest

    def poll_scans(self) -> [scan_pb2.Scan2d]:
        """Override polling of scans."""
        scan_path = self._get_latest_file(self.SCAN_EXT)
        if (scan_path and not self._old_scan_path or
                scan_path != self._old_scan_path):
            scans = load_scans_from_file(scan_path)
            scans = [ct.correct_scan(scan, self._latest_scan_params)
                     for scan in scans]
            if scans:
                self._old_scan_path = scan_path
                self._old_scans = scans
        return self._old_scans

    def poll_spec(self) -> spec_pb2.Spec1d:
        """Override spec polling."""
        spec_path = self._get_latest_file(self.SPEC_EXT)

        if (spec_path and not self._old_spec_path or
                spec_path != self._old_spec_path):
            spec = load_spec_from_file(spec_path)
            spec = ct.correct_spec(spec, self._latest_probe_pos)
            if spec:
                self._old_spec_path = spec_path
                self._old_spec = spec
        return self._old_spec

    # --- Parameter Handlers --- #
    # Here, we override composite setters / getters to avoid unnecessary
    # get/set calls (look at this issue in params.py).
    PHYSICAL_SCAN_PARAMS = [MicroscopeParameter.SCAN_SIZE_X,
                            MicroscopeParameter.SCAN_SIZE_Y,
                            MicroscopeParameter.SCAN_TOP_LEFT_X,
                            MicroscopeParameter.SCAN_TOP_LEFT_Y,
                            MicroscopeParameter.SCAN_ANGLE]
    DIGITAL_SCAN_PARAMS = [MicroscopeParameter.SCAN_RESOLUTION_X,
                           MicroscopeParameter.SCAN_RESOLUTION_Y]

    def on_set_scan_params(self, scan_params: scan_pb2.ScanParameters2d
                           ) -> control_pb2.ControlResponse:
        """Override to avoid many get calls."""
        # Populate and send physical scan params
        class_name = self.param_handler._get_param_info(
            MicroscopeParameter.SCAN_SIZE_X).class_name
        req_rep = self.param_handler._get_setter_req_rep(class_name)

        # Top Left -> Center correction
        center_x = params.top_left_to_center(scan_params.spatial.roi.top_left.x,
                                             scan_params.spatial.roi.size.x)
        center_y = params.top_left_to_center(scan_params.spatial.roi.top_left.y,
                                             scan_params.spatial.roi.size.y)

        vals = [scan_params.spatial.roi.size.x,
                scan_params.spatial.roi.size.y,
                center_x,
                center_y,
                scan_params.spatial.roi.angle]
        units = [scan_params.spatial.length_units,
                 scan_params.spatial.length_units,
                 scan_params.spatial.length_units,
                 scan_params.spatial.length_units,
                 scan_params.spatial.angular_units]
        req_rep.req = self.param_handler.populate_req(
            req_rep.req, self.PHYSICAL_SCAN_PARAMS, vals, units)
        self.param_handler.send_request(req_rep.req, req_rep.rep)

        # Populate and send resolution (this requires a get due to
        # channels data in Nanonis struct)
        class_name = self.param_handler._get_param_info(
            MicroscopeParameter.SCAN_RESOLUTION_X).class_name
        req_rep = self.param_handler._get_setter_req_rep(class_name)
        req_rep.req = self.param_handler._obtain_base_set_req(class_name)
        vals = [scan_params.data.shape.x,
                scan_params.data.shape.y]
        units = [None, None]
        req_rep.req = self.param_handler.populate_req(
            req_rep.req, self.DIGITAL_SCAN_PARAMS, vals, units)
        self.param_handler.send_request(req_rep.req, req_rep.rep)
        return control_pb2.ControlResponse.REP_SUCCESS

    def poll_scan_params(self) -> scan_pb2.ScanParameters2d:
        """Override to avoid many get calls."""
        length_units = self.param_handler.get_unit(
            params.MicroscopeParameter.SCAN_SIZE_X)
        angular_units = self.param_handler.get_unit(
            params.MicroscopeParameter.SCAN_ANGLE)

        # Get physical scan params
        class_name = self.param_handler._get_param_info(
            MicroscopeParameter.SCAN_SIZE_X).class_name
        req_rep = self.param_handler._get_getter_req_rep(class_name)
        phys_rep = self.param_handler.set_param_reqrep(req_rep)

        # Get digital scan params
        class_name = self.param_handler._get_param_info(
            MicroscopeParameter.SCAN_RESOLUTION_X).class_name
        req_rep = self.param_handler._get_getter_req_rep(class_name)
        digital_rep = self.param_handler.set_param_reqrep(req_rep)

        # Center -> Top Left correction
        top_left_x = params.center_to_top_left(phys_rep.center_x,
                                               phys_rep.width)
        top_left_y = params.center_to_top_left(phys_rep.center_y,
                                               phys_rep.height)

        # Populate scan params
        scan_params = scan_pb2.ScanParameters2d()
        scan_params.spatial.roi.size.x = phys_rep.width
        scan_params.spatial.roi.size.y = phys_rep.height
        scan_params.spatial.roi.top_left.x = top_left_x
        scan_params.spatial.roi.top_left.y = top_left_y
        scan_params.spatial.roi.angle = phys_rep.angle
        scan_params.spatial.length_units = length_units
        scan_params.spatial.angular_units = angular_units

        scan_params.data.shape.x = digital_rep.pixels
        scan_params.data.shape.y = digital_rep.lines

        return scan_params

    def set_setup_properties(self, props: params.SetupProperties):
        """Set the current SetupProperties."""
        # Prep scan properties
        class_name = self.param_handler._get_param_info(
            params.NanonisParam.SCAN_AUTO_SAVE).class_name

        scan_req = self.param_handler._obtain_base_set_req(class_name)
        scan_req.continuous_scan = props.scan_continuous_scan
        scan_req.auto_save = props.scan_auto_save
        scan_rep = self.param_handler._get_setter_req_rep(class_name).rep
        self.param_handler.send_request(scan_req, scan_rep)

        # Prep spec properties
        class_name = self.param_handler._get_param_info(
            params.NanonisParam.Z_SPEC_AUTO_SAVE).class_name
        z_req = self.param_handler._obtain_base_set_req(class_name)
        z_req.auto_save = props.spec_auto_save
        z_req.show_save_dialog = props.spec_save_dialog
        z_rep = self.param_handler._get_setter_req_rep(class_name).rep
        self.param_handler.send_request(z_req, z_rep)

        class_name = self.param_handler._get_param_info(
            params.NanonisParam.BIAS_SPEC_AUTO_SAVE).class_name
        bias_req = self.param_handler._obtain_base_set_req(class_name)
        bias_req.auto_save = props.spec_auto_save
        bias_req.show_save_dialog = props.spec_save_dialog
        bias_rep = self.param_handler._get_setter_req_rep(class_name).rep
        self.param_handler.send_request(bias_req, bias_rep)

    def poll_scope_state(self) -> scan_pb2.ScopeState:
        """Implement."""
        scan_state = self.param_handler.get_param(
            params.NanonisParam.SCAN_STATUS)
        if scan_state:
            return scan_pb2.ScopeState.SS_SCANNING

        bias_spec_state = self.param_handler.get_param(
            params.NanonisParam.BIAS_SPEC_STATUS)
        if bias_spec_state:
            return scan_pb2.ScopeState.SS_SPEC

        z_spec_state = self.param_handler.get_param(
            params.NanonisParam.Z_SPEC_STATUS)
        if z_spec_state:
            return scan_pb2.ScopeState.SS_SPEC

        return scan_pb2.ScopeState.SS_FREE


def _init_action_handler(client: NanonisClient
                         ) -> actions.NanonisActionHandler:
    """Initialize Nanonis action handler pointing to default config."""
    actions_config_path = os.path.join(os.path.dirname(__file__),
                                       DEFAULT_ACTIONS_FILENAME)
    return actions.NanonisActionHandler(
        client, actions_config_path=actions_config_path)


def _init_param_handler(client: NanonisClient
                        ) -> params.NanonisParameterHandler:
    """Initialize Nanonis param handler pointing to default config."""
    params_config_path = os.path.join(os.path.dirname(__file__),
                                      DEFAULT_PARAMS_FILENAME)
    return params.NanonisParameterHandler(
        client, params_config_path=params_config_path)


def load_scans_from_file(scan_path: str
                         ) -> list[scan_pb2.Scan2d] | None:
    """Load Nanonis scan, filling in info possible from file only.

    NOTE: We follow the suggestions of config_translator and use correct_scan()
    in the calling method (avoids any coordinate system differences).
    We still need to set the filename, however.

    Args:
        scan_path: path to the scan.

    Returns:
        loaded scans in scan_pb2 format (one scan per channel). None if
        dataset is empty.

    Raises:
        Unknown/unforeseen read error.
    """
    logger.debug(f"Getting datasets from {scan_path} (each dataset"
                 " is a channel).")
    reader = sr.NanonisSXMReader(scan_path)
    datasets = reader.read()

    if datasets:
        scans = []
        for ds in datasets:
            # BUG WORKAROUND: scifireaders does not properly load the
            # scan data! The data is read originally in the same manner
            # as gwyddion, which causes the origin to be misplaced. In an
            # attempt to fix this, the IgorIBWReader performs np.rot90(m, 3),
            # i.e. rotates by 90 \deg 3x counter-clockwise. This *mostly* works,
            # except that it swaps the axes!
            # To workaround this, we swap the axes back. The more 'proper' fix
            # would be to simple perform an np.flip(m, 0) rather than these
            # operations.
            swap_ds = ds.swapaxes(0, 1)
            scan = conv.convert_sidpy_to_scan_pb2(swap_ds)

            # Setting filename. All else is done by correct_scan()
            # (recommended to ensure coordinate system consistency).
            scan.filename = scan_path
            scans.append(scan)
        return scans
    return None


def load_spec_from_file(fname: str,
                        ) -> spec_pb2.Spec1d | None:
    """Load Spec1d from provided filename (None on failure).

    NOTE: We follow the suggestions of config_translator and use correct_spec()
    in the calling method (avoids any coordinate system differences). In this
    case, probe position is not available in the saved data so we need it.

    Args:
        fname: path to spec file.

    Returns:
        Spec1d if loaded properly, None if spec file was empty.

    Raises:
        Unknown/unforeseen read error.
    """
    reader = sr.NanonisDatReader(fname)
    datasets = reader.read()

    spec = conv.convert_sidpy_to_spec_pb2(datasets)
    spec.filename = fname

    return spec
