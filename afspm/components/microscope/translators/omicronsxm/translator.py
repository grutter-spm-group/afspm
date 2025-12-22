"""Handles device communication with the Omicron SXM controller."""

import logging
import os
from glob import glob

from ...params import (ParameterHandler,
                       DEFAULT_PARAMS_FILENAME)
from ...actions import (ActionHandler,
                        DEFAULT_ACTIONS_FILENAME,
                        MicroscopeAction)
from ...translator import get_file_modification_datetime
from ... import config_translator as ct

from .....utils import array_converters as conv

from .....io.protos.generated import scan_pb2
from .....io.protos.generated import spec_pb2
from .....io.protos.generated import geometry_pb2
from .....io.protos.generated import control_pb2

from . import params
from . import actions
from . import sxm
from . import reader_sxm


logger = logging.getLogger(__name__)


# Attributes from the read scan file (differs from params,
# which contains UUIDs for getting/setting parameters).
SCAN_ATTRIB_ANGLE = 'Angle'
# Hardcoded, even though it is also in params.toml. For loading scan.
SCAN_ANGLE_UNIT = 'degrees'


class SXMTranslator(ct.ConfigTranslator):
    """Handles device communication with the Scienta Omicron SXM controller.

    The SXMTranslator communicates with the Asylum Research software via the
    XopClient, which sends/receives JSON messages over a zmq interface as
    defined by the Allen Institute's ZeroMQ-XOP project:
    https://github.com/AllenInstitute/ZeroMQ-XOP

    Notes:
    - In SXM, the spec position and probe position do not need to align
    *until* a spec is run. To be consistent with our expectations, we set
    both of these whenever the probe position is set. On a get, we grab
    from the actual probe position.

    Attributes:
        _old_scans: the last scans, to send out if it has not changed.
        _old_scan_path: the prior scan filepath. We use this to avoid loading
            the same scans multiple times.
        _old_spec: the last spec, to send out if it has not changed.
        _old_spec_path: the prior spec filepath. We use this to avoid loading
            the same spectroscopies multiple times.
        _scope_state: holds the current client.
        _client: SXM client.
    """

    INI_SECTION_SAVE = 'Save'
    INI_ITEM_PATH = 'Path'

    def __init__(self, param_handler: ParameterHandler = None,
                 action_handler: ActionHandler = None,
                 client: sxm.DDEClient = None,
                 **kwargs):
        """Init our translator."""
        self._old_scan_path = None
        self._old_scans = []
        self._old_spec_path = None
        self._old_spec = None
        self._scope_state = scan_pb2.ScopeState.SS_FREE
        self._client = client

        # Default initialization of handler
        kwargs = self._init_handlers(client, param_handler, action_handler,
                                     **kwargs)
        # Tell parent class that SXM *does not* detect moving
        kwargs[ct.DETECTS_MOVING_KEY] = False
        super().__init__(**kwargs)
        self._init_spec_settings()

    def _init_handlers(self, client: sxm.DDEClient,
                       param_handler: ParameterHandler,
                       action_handler: ActionHandler,
                       **kwargs) -> dict:
        """Init handlers and update kwargs."""
        if not client:
            client = sxm.DDEClient("SXM", "Remote")
        self._register_scan_spec_end_callbacks(client)

        if not param_handler:
            param_handler = _init_param_handler(client)
            kwargs[ct.PARAM_HANDLER_KEY] = param_handler
        if not action_handler:
            action_handler = _init_action_handler(client)
            kwargs[ct.ACTION_HANDLER_KEY] = action_handler
        return kwargs

    def _register_scan_spec_end_callbacks(self, client: sxm.DDEClient):
        """Ensure we detect when scans/specs end, to update scope state."""
        client.register_spect_save_callback(self.on_scan_spec_end)
        client.register_scan_end_callback(self.on_scan_spec_end)

    def _on_scan_spec_end(self):
        """Return scope state to free when scan/spec ends.

        The main scope state logic is handled in on_action_request()
        and on_scan_spec_end().
        """
        self._scope_state = scan_pb2.ScopeState.SS_FREE

    def _init_spec_settings(self):
        """Set up spec defaults: autosave and do not repeat."""
        self.param_handler.set_param(params.SXMParam.SPEC_AUTOSAVE, 1)
        self.param_handler.set_param(params.SXMParam.SPEC_REPEAT, 0)

    def switch_feedback_mode(self, mode: params.FeedbackMode):
        """Switch to using appropriate feedback mode."""
        self.param_handler._switch_feedback_mode(mode)

    def poll_scope_state(self) -> scan_pb2.ScopeState:
        """Poll the controller for the current scope state.

        NOTE: We cannot detect whether the motor is running via SXMRemote.
        Throws a MicroscopeError on failure.
        """
        return self._scope_state

    def _get_latest_file(self, spec: bool) -> str | None:
        """Return the filepath for the latest scan/spec.

        Args:
            spec: if true, we grab the latest spec. If false, the latest
                scan.

        Raises:
            ValueError if the file structure is incorrect (i.e. there are
                no/several metadata files in a sub-directory).
        """
        latest_dir = self._client.get_ini_entry(self.INI_SECTION_SAVE,
                                                self.INI_ITEM_PATH)
        ext = reader_sxm.SPEC_DATA_EXT if spec else reader_sxm.SCAN_METADATA_EXT
        ext = "*" + ext
        try:
            files = sorted(glob(os.path.join(latest_dir,
                                             os.path.join(os.sep, ext))),
                           key=os.path.getmtime)  # Sorted by access time
        except ValueError:
            # No files currently showing
            return None
        return files[0]  # Returning newest matching file in scan dir.

    def poll_scans(self) -> [scan_pb2.Scan2d]:
        """Override polling of scans."""
        scan_path = self._get_latest_file(spec=False)  # Actually md path
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
        spec_path = self._get_latest_file(spec=True)
        if (spec_path and not self._old_spec_path or
                spec_path != self._old_spec_path):
            spec = load_spec_from_file(spec_path)
            spec = ct.correct_spec(spec, self._latest_probe_pos)
            if spec:
                self._old_spec_path = spec_path
                self._old_spec = spec
        return self._old_spec

    def on_action_request(self, action: control_pb2.ActionMsg
                          ) -> control_pb2.ControlResponse:
        """Override to change state for scan/specs.

        Since we can mainly detect when scans/specs *end*, we
        use successful action requests to handle the 'start' of
        a scan/spec.
        """
        rep = super().on_action_request(action)
        if rep == control_pb2.ControlResponse.REP_SUCCESS:
            if action.action == MicroscopeAction.START_SCAN:
                self._scope_state = scan_pb2.ScopeState.SS_SCANNING
            elif action.action == MicroscopeAction.STOP_SCAN:
                self._scope_state = scan_pb2.ScopeState.SS_FREE
            elif action.action == MicroscopeAction.START_SPEC:
                self._scope_state = scan_pb2.ScopeState.SS_SPEC


# TODO: Consider pulling client up to translator level if it needs resetting?
def _init_action_handler(client: sxm.DDEClient
                         ) -> actions.AsylumActionHandler:
    """Initialize Asylum action handler pointing to defulat config."""
    actions_config_path = os.path.join(os.path.dirname(__file__),
                                       DEFAULT_ACTIONS_FILENAME)
    return actions.AsylumActionHandler(actions_config_path, client)


def _init_param_handler(client: sxm.DDEClient
                        ) -> params.AsylumParameterHandler:
    """Initialize Asylum action handler pointing to defulat config."""
    params_config_path = os.path.join(os.path.dirname(__file__),
                                      DEFAULT_PARAMS_FILENAME)
    return params.AsylumParameterHandler(params_config_path, client)


def load_scans_from_file(md_path: str
                         ) -> list[scan_pb2.Scan2d] | None:
    """Load SXM scan, filling in info possible from file only.

    Args:
        md_path: path to the scan metadata.

    Returns:
        loaded scans in scan_pb2 format (one scan per channel). None if
        dataset is empty or failure loading scan.
    """
    try:
        reader = reader_sxm.SXMScanReader(md_path)
        datasets = reader.read(verbose=False)
    except Exception as exc:
        logger.error(f"Failure loading scan at {md_path}: {exc}")
        return None

    if datasets:
        scans = []
        for ds in datasets:
            file_path = os.path.join(os.path.dirname(md_path),
                                     ds.metadata[reader_sxm.MD_SCAN_FILENAME])
            scan = conv.convert_sidpy_to_scan_pb2(ds)

            # Set ROI angle, timestamp, filename
            scan.params.spatial.roi.angle = ds.metadata[
                SCAN_ATTRIB_ANGLE]
            scan.params.spatial.angular_units = SCAN_ANGLE_UNIT

            ts = get_file_modification_datetime(file_path)
            scan.timestamp.FromDatetime(ts)

            scan.filename = file_path
            scans.append(scan)
        return scans
    return None


def load_spec_from_file(fname: str,
                        ) -> spec_pb2.Spec1d | None:
    """Load Spec1d from provided filename (None on failure).

    Args:
        fname: path to spec file.

    Returns:
        Spec1d if loaded properly, None if spec file was empty or exception
        thrown when reading.
    """
    try:
        reader = reader_sxm.SXMSpecReader(fname)
        datasets = reader.read(verbose=False)

        spec = conv.convert_sidpy_to_spec_pb2(datasets)
        spec.filename = fname

        # Correct probe position
        probe_x = datasets[0].original_metadata[reader_sxm.MD_PROBE_POS_X]
        probe_y = datasets[0].original_metadata[reader_sxm.MD_PROBE_POS_Y]
        units = reader_sxm.MD_POS_UNITS
        point = geometry_pb2.Point2d(x=float(probe_x), y=float(probe_y))
        spec.position = spec_pb2.ProbePosition(point, units=units)

        return spec
    except Exception:
        logger.error(f'Could not read spec fname {fname}.'
                     'Got error.', exc_info=True)
        return None
