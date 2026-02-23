"""Handles device communication with the Omicron SXM controller."""

import logging
import os
from glob import glob

from ...params import (ParameterHandler,
                       DEFAULT_PARAMS_FILENAME)
from ...actions import (ActionHandler,
                        DEFAULT_ACTIONS_FILENAME,
                        MicroscopeAction)
from ... import config_translator as ct

from .....utils import array_converters as conv

from .....io.protos.generated import scan_pb2
from .....io.protos.generated import spec_pb2
from .....io.protos.generated import control_pb2

from . import params
from . import actions
from . import sxm
from . import reader


logger = logging.getLogger(__name__)


class SXMTranslator(ct.ConfigTranslator):
    """Handles device communication with the Scienta Omicron SXM controller.

    Omicron Research SXM allows communication with the controller software
    via DDE, a Windows inter-process communication interface.
    They also provide (on top of this) a Python interface.
    The local module sxm is our modified version of this interface.

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
        _probe_pos_moving: bool, holds whether we have been moving the probe
            pos.

        _prior_spec_mode: index for prior spectroscopy mode. Saved for when
            we need to run a 'fake spec'.
        _prior_spec_vals: prior spectroscopy mode settings. Saved for when
            we need to run a 'fake spec'.

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
        self._probe_pos_moving = False

        self._prior_spec_mode = None
        self._prior_spec_vals = None

        # Default initialization of handler
        kwargs = self._init_handlers(client, param_handler, action_handler,
                                     **kwargs)

        # Tell parent class that SXM *does not* detect moving
        kwargs[ct.DETECTS_MOVING_KEY] = False
        # Tell parent class that SXM requires setting y before x.
        kwargs[ct.SET_X_BEFORE_Y_KEY] = False
        super().__init__(**kwargs)

        # Grab client from parameter handler, in case no client was provided
        # (and it was init'ed in _init_handlers).
        self._client = self.param_handler.client

        self._init_scan_settings()
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

    def _validate_required_actions_exist(self):
        """Override to allow to run. Throw warning on startup."""
        logger.warning('SXMTranslator does not support STOP_SCAN or STOP_SPEC!'
                       ' If API support is added, update actions.toml and'
                       ' remove this override. Allowing to continue.')

    def _register_scan_spec_end_callbacks(self, client: sxm.DDEClient):
        """Ensure we detect when scans/specs end, to update scope state."""
        client.register_spect_save_callback(self._on_spec_end)
        client.register_scan_end_callback(self._on_scan_end)

    def _on_scan_end(self):
        """Return scope state to free when scan ends.

        The main scope state logic is handled in on_action_request()
        and on_scan_end().
        """
        self._scope_state = scan_pb2.ScopeState.SS_FREE

    def _on_spec_end(self, filename: str):
        """Return scope state to free when spec ends.

        The main scope state logic is handled in on_action_request()
        and on_spec_end().

        On a spectroscopy ending, we call _handle_probe_pos_move() if
        it was a 'fake' spectroscopy to move the probe.
        """
        self._scope_state = scan_pb2.ScopeState.SS_FREE
        if self._probe_pos_moving:
            self._delete_fake_spec(filename)
            self._end_probe_pos_move()
            self._probe_pos_moving = False

    def _delete_fake_spec(self, filename: str):
        latest_dir = self._client.get_ini_entry(self.INI_SECTION_SAVE,
                                                self.INI_ITEM_PATH)
        spec_path = os.path.join(latest_dir, filename)
        if os.path.isfile(spec_path):
            os.remove(spec_path)

    def _init_scan_settings(self):  # TODO: Can we turn continuous scan OFF?
        """Set up scan defaults: autosave."""
        self.param_handler.set_param(params.SXMParam.SCAN_AUTOSAVE, 1)

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
        if self._probe_pos_moving:  # Avoid SS_SPEC while forcing move.
            return scan_pb2.ScopeState.SS_MOVING
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
        ext = reader.SPEC_DATA_EXT if spec else reader.SCAN_METADATA_EXT
        file_form = "*" + ext
        try:
            files = sorted(glob(os.path.join(latest_dir, file_form)),
                           key=os.path.getmtime)  # Sorted by access time
        except ValueError:
            # No files currently showing
            return None
        return files[-1] if files else None  # Get latest

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
        if self._probe_pos_moving:  # If moving, do not check.
            return self._old_spec

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
            elif action.action == MicroscopeAction.START_SPEC:
                self._scope_state = scan_pb2.ScopeState.SS_SPEC
        return rep

    def on_set_probe_pos(self, probe_position: spec_pb2.ProbePosition
                         ) -> control_pb2.ControlResponse:
        """Override for proper pos moving."""
        rep = super().on_set_probe_pos(probe_position)
        if rep == control_pb2.ControlResponse.REP_SUCCESS:
            self._start_probe_pos_move()
            self._probe_pos_moving = True
        return rep

    # For fake spectroscopy -- probe pos move
    DZ_SETTING_UUIDS = [params.SXMParam.DZ_DELAY1,
                        params.SXMParam.DZ_DELAY2,
                        params.SXMParam.DZ_dz1,
                        params.SXMParam.DZ_dz1]
    DZ_FAKE_VALS = [1.0, 1.0, 0.0, 0.0]

    def _start_probe_pos_move(self):
        """Start a probe movement.

        The SXM controller does not move the probe position on set.
        In fact, the recommended way to move the probe is to force a
        spectroscopy!

        This method does that, but we have to do a bunch of homework
        before actually running the spect:
        - We store the current spectroscopy mode;
        - We change to our 'fake spect' mode (D(z)), store the
        current settings for that mode, and set to our 'fake spect'
        settings (no z motion, 1 ms steps);
        - Run spect.

        Note that separately we will delete this fake spect once it
        finishes. We cannot disable saving because the only way
        we know a spectroscopy ends is due to it saving.
        """
        spec_mode_uuid = params.SXMParam.SPEC_MODE
        self._prior_spec_mode = self.param_handler.get_param()
        self.param_handler.set_param(spec_mode_uuid,
                                     params.SPEC_MODE_DZ_IDX)

        # Get / set D(z) spec settings
        dz_prior_vals = []
        for uuid, desired_val in zip(self.DZ_SETTING_UUIDS,
                                     self.DZ_FAKE_VALS):
            dz_prior_vals.append(self.param_handler.get_param(uuid))
            self.param_handler.set_param(uuid, desired_val)
        self._prior_spec_vals = dz_prior_vals

        # Fake spect
        self.action_handler.request_action(MicroscopeAction.START_SPEC)

    def _end_probe_pos_move(self):
        """End a probe pose movement.

        Here, we:
        - Return to the prior D(z) settings;
        - Switch to the prior spect mode;
        """
        for uuid, prior_val in zip(self.DZ_SETTING_UUIDS,
                                   self._prior_spec_vals):
            self.param_handler.set_param(uuid, prior_val)
        self.param_handler.set_param(params.SXMParam.SPEC_MODE,
                                     self._prior_spec_mode)
        self._prior_spec_mode = None
        self._prior_spec_vals = None


def _init_action_handler(client: sxm.DDEClient
                         ) -> actions.SXMActionHandler:
    """Initialize SXM action handler pointing to default config."""
    actions_config_path = os.path.join(os.path.dirname(__file__),
                                       DEFAULT_ACTIONS_FILENAME)
    return actions.SXMActionHandler(
        client, actions_config_path=actions_config_path)


def _init_param_handler(client: sxm.DDEClient
                        ) -> params.SXMParameterHandler:
    """Initialize SXM action handler pointing to default config."""
    params_config_path = os.path.join(os.path.dirname(__file__),
                                      DEFAULT_PARAMS_FILENAME)
    return params.SXMParameterHandler(
        client, params_config_path=params_config_path)


def load_scans_from_file(md_path: str
                         ) -> list[scan_pb2.Scan2d] | None:
    """Load SXM scan, filling in info possible from file only.

    NOTE: We follow the suggestions of config_translator and use correct_scan()
    in the calling method (avoids any coordinate system differences).
    We still need to set the filename, however.

    Args:
        md_path: path to the scan metadata.

    Returns:
        loaded scans in scan_pb2 format (one scan per channel). None if
        dataset is empty.

    Raises:
        Unknown/unforeseen read error.
    """
    sxm_reader = reader.SXMScanReader(md_path)
    datasets = sxm_reader.read()

    if datasets:
        scans = []
        for ds in datasets:
            file_path = os.path.join(
                os.path.dirname(md_path),
                ds.original_metadata[reader.MD_SCAN_FILENAME])
            scan = conv.convert_sidpy_to_scan_pb2(ds)
            scan.filename = file_path
            scans.append(scan)
        return scans
    return None


def load_spec_from_file(fname: str,
                        ) -> spec_pb2.Spec1d | None:
    """Load Spec1d from provided filename (None on failure).

    NOTE: We follow the suggestions of config_translator and use correct_spec()
    in the calling method (avoids any coordinate system differences).

    Args:
        fname: path to spec file.

    Returns:
        Spec1d if loaded properly, None if spec file was empty.

    Raises:
        Unknown/unforeseen read error.
    """
    sxm_reader = reader.SXMSpecReader(fname)
    datasets = sxm_reader.read()

    spec = conv.convert_sidpy_to_spec_pb2(datasets)
    spec.filename = fname
    return spec
