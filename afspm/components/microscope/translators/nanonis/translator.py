"""Handles device communication with the Nanonis controller."""

import os.path
import glob
import logging

import SciFiReaders as sr

from afspm.components.microscope.params import (ParameterHandler,
                                                DEFAULT_PARAMS_FILENAME)
from afspm.components.microscope.actions import (ActionHandler,
                                                 DEFAULT_ACTIONS_FILENAME)

from afspm.components.microscope import config_translator as ct
from afspm.utils import array_converters as conv

from afspm.io.protos.generated import scan_pb2
from afspm.io.protos.generated import spec_pb2

from . import params
from . import actions
from .client import NanonisClient
from .message import base, spectroscopy


logger = logging.getLogger(__name__)


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
        images = sorted(glob.glob(file_path + os.sep + "*"
                                  + ext),
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
    # TODO: Consider implementing?

    def set_setup_properties(self, props: params.SetupProperties):
        """Set the current SetupProperties."""
        # Prep scan properties
        scan_props_uuid = self.param_handler._get_param_info(
            params.NanonisParam.SCAN_AUTO_SAVE).uuid

        scan_req = self.param_handler._obtain_base_set_req(scan_props_uuid)
        scan_req.continuous_scan = props.scan_continuous_scan
        scan_req.auto_save = props.scan_auto_save
        scan_rep = self.param_handler._get_setter_req_rep(scan_props_uuid).rep
        params.send_request(self.param_handler._client, scan_req, scan_rep)

        # Prep spec properties
        z_spec_props_uuid = self.param_handler._get_param_info(
            params.NanonisParam.Z_SPEC_AUTO_SAVE).uuid
        z_req = self.param_handler._obtain_base_set_req(z_spec_props_uuid)
        z_req.auto_save = props.spec_auto_save
        z_req.show_save_dialog = props.spec_save_dialog
        z_rep = self.param_handler._get_setter_req_rep(z_spec_props_uuid).rep
        params.send_request(self.param_handler._client, z_req, z_rep)

        bias_spec_props_uuid = self.param_handler._get_param_info(
            params.NanonisParam.BIAS_SPEC_AUTO_SAVE).uuid
        bias_req = self.param_handler._obtain_base_set_req(
            bias_spec_props_uuid)
        bias_req.auto_save = props.spec_auto_save
        bias_req.show_save_dialog = props.spec_save_dialog
        bias_rep = self.param_handler._get_setter_req_rep(
            bias_spec_props_uuid).rep
        params.send_request(self.param_handler._client, bias_req, bias_rep)

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
        dataset is empty or failure loading scan.
    """
    logger.debug(f"Getting datasets from {scan_path} (each dataset"
                 " is a channel).")
    try:
        reader = sr.NanonisSXMReader(scan_path)
        datasets = reader.read()
    except Exception as exc:
        logger.error(f"Failure loading scan at {scan_path}: {exc}")
        return None

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
        Spec1d if loaded properly, None if spec file was empty or exception
        thrown when reading.
    """
    try:
        reader = sr.NanonisDatReader(fname)
        datasets = reader.read()

        spec = conv.convert_sidpy_to_spec_pb2(datasets)
        spec.filename = fname

        return spec
    except Exception:
        logger.error(f'Could not read spec fname {fname}.'
                     'Got error.', exc_info=True)
        return None
