"""Handles device communication with the Omicron SXM controller."""

import logging
import os
from glob import glob
from dataclasses import astuple

from ...params import (ParameterHandler,
                       DEFAULT_PARAMS_FILENAME,
                       MicroscopeError)
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
    - In order to move the probe on set_probe_pos(), we have to 'fake' a
    spectroscopy (this is the suggested way to move the probe). Because of
    this, we have a _fake_spectroscopy_settings input argument, consisting
    of the settings for the spectroscopy mode we are using to move. One would
    expect/want these to be minimally invasive and quick. When this 'fake' spec
    has finished, we delete it so it does not contaminate our experimental data.
    - There is no way to poll for the spec state, so we have to use a semi-ugly
    state machine in here: we switch to SS_SPEC when START_SPEC succeeds, and
    switch back to SS_FREE when it ends (detected via a spec save callback).
    - The START_SPEC command is not asynchronous! It returns an ACK once the
    spec has ended, not once it has started. To avoid this weirdness causing
    logic issues, we pause polling during SS_SPEC.
    - The probe position getter gets the *actual* position at any instance in
    time. This diverges from how the getter works with other translators, where
    it tells us where we have set it to be. To minimize deviations from other
    translators, we thus pause poll_probe_pos if we are not free.

    Attributes:
        _old_scans: the last scans, to send out if it has not changed.
        _old_scan_path: the prior scan filepath. We use this to avoid loading
            the same scans multiple times.
        _old_spec: the last spec, to send out if it has not changed.
        _old_spec_path: the prior spec filepath. We use this to avoid loading
            the same spectroscopies multiple times.
        _probe_pos_moving: bool, holds whether we have been moving the probe
            pos.

        _spectroscopy_mode: mode we want to be in when running spectroscopies.
        _fake_spectroscopy_settings: settings for our fake spectroscopy, used
            to move the probe position. Can be either SpectroscopySettingsHeight
            or SpectroscopySettingsBias.

        _client: SXM client.
    """

    INI_SECTION_SAVE = 'Save'
    INI_ITEM_PATH = 'Path'

    DEFAULT_SPEC_MODE = params.SpectroscopyMode.X_U
    DEFAULT_FAKE_X_U = params.SpectroscopySettingsBias(1.0, 1.0, 0.0, 0.0)
    DEFAULT_FAKE_X_Z = params.SpectroscopySettingsHeight(1.0, 1.0, 0.0, 0.0,
                                                         0.0)
    DEFAULT_FAKE_SPEC_SETTINGS = DEFAULT_FAKE_X_Z

    def __init__(self, param_handler: ParameterHandler = None,
                 action_handler: ActionHandler = None,
                 client: sxm.DDEClient = None,
                 spectroscopy_mode: params.SpectroscopyMode = DEFAULT_SPEC_MODE,
                 fake_spectroscopy_settings: params.SpectroscopySettingsBias |
                 params.SpectroscopySettingsHeight = DEFAULT_FAKE_SPEC_SETTINGS,
                 **kwargs):
        """Init our translator."""
        self._old_scan_path = None
        self._old_scans = []
        self._old_spec_path = None
        self._old_spec = None
        self._probe_pos_moving = False

        self._spectroscopy_mode = spectroscopy_mode
        self._fake_spectroscopy_settings = fake_spectroscopy_settings

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

        # Set up our save settings (spec and scan) and configure our
        # spectroscopy settings.
        self._init_save_settings()
        self._init_spec_settigs()

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

    def _init_scan_settings(self):
        """Set up scan / spec defaults: autosave and do not repeat."""
        self.param_handler.set_param(params.SXMParam.SCAN_AUTOSAVE, 1)
        # TODO: Can we turn continuous scan OFF?

        self.param_handler.set_param(params.SXMParam.SPEC_AUTOSAVE, 1)
        self.param_handler.set_param(params.SXMParam.SPEC_REPEAT, 0)

    def _init_spec_settings(self):
        """On startup, set 'fake' spec settings and switch to real spec mode.

        First, we switch to our 'fake' spectroscopy mode and set its parameters
        according to our 'fake' settings. The goal here is for the 'fake' spec
        to be a short as possible and minimally invasive on the project.

        Then, we switch to our actual spectroscopy, which we want to be using
        when calling START_SPEC.
        """
        self.set_spectroscopy_settings(self._fake_spectroscopy_settings)
        self.set_spectroscopy_mode(self._spectroscopy_mode)

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
        # Remove double-quotes, as they break os.path.join
        if latest_dir.startswith('"') and latest_dir.endswith('"'):
            latest_dir = latest_dir[1:-1]
        ext = reader.SPEC_DATA_EXT if spec else reader.SCAN_METADATA_EXT
        file_form = "*" + ext
        try:
            files = sorted(glob(os.path.join(latest_dir, file_form)),
                           key=os.path.getmtime)  # Sorted by access time
        except ValueError:
            # No files currently showing
            return None
        return files[-1] if files else None  # Get latest

    def poll_scope_state(self) -> scan_pb2.ScopeState:
        """Poll the controller for the current scope state.

        NOTE:
        - We cannot detect whether the motor is running via sxm.
        - We cannot detect SS_SPEC via sxm, so we have to have state logic
        in this class.
        Throws a MicroscopeError on failure.
        """
        if self._probe_pos_moving:  # Avoid SS_SPEC while forcing move.
            return scan_pb2.ScopeState.SS_MOVING
        elif self.scope_state is scan_pb2.ScopeState.SS_SPEC:
            # No way to poll spec, so ugly hack.
            return scan_pb2.ScopeState.SS_SPEC
        else:
            state = self.param_handler.get_param(params.SXMParam.SCAN_STATE)
            return (scan_pb2.ScopeState.SS_SCANNING if state
                    else scan_pb2.ScopeState.SS_FREE)

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

    def poll_probe_pos(self) -> spec_pb2.ProbePosition | None:
        """Override to skip when not SS_FREE.

        We need to do this because our probe position getter returns the
        actual position of the probe at any point in time. This means
        that we send many probe position updates during, e.g., a scan.

        The current expectation is that probe pos get will tell us where
        the probe will be for spectroscopies / tip manipulation operations,
        and that a set() will result in SS_MOVING until the probe is at this
        location. In short, while the current behaviour is nice, it is not
        what our black-box expectations are.

        With this override, we meet our black-box expectations.
        """
        if self.scope_state in [scan_pb2.ScopeState.SS_FREE,
                                scan_pb2.ScopeState.SS_UNDEFINED]:
            return super().poll_probe_pos()
        return self.probe_pos

    def _handle_polling_device(self):
        """Override to not poll while spectroscopy is running.

        We need to do this because the call to start spect does not
        return until the spectroscopy has finished, and this breaks
        our sxm client (because at some point, we receive the spect
        finished response instead of a poll we were doing, causing
        a crash).

        Not great, pretty ugly. Oh well.
        """
        if self.scope_state is not scan_pb2.ScopeState.SS_SPEC:
            super()._handle_polling_device()
        else:
            sxm.loop()  # Still check for callbacks

    def on_action_request(self, action: control_pb2.ActionMsg
                          ) -> control_pb2.ControlResponse:
        """Override to change state for spec.

        There is no way to poll the spec state via the API, so we
        have to resort to this ugly hack.
        """
        rep = super().on_action_request(action)
        if rep == control_pb2.ControlResponse.REP_SUCCESS:
            if action.action == MicroscopeAction.START_SPEC:
                self.scope_state = scan_pb2.ScopeState.SS_SPEC
                # Send out message (our polling is disabled for the
                # duration of SS_SPEC).
                self._force_send_scope_state(self.scope_state)
        return rep

    def on_set_probe_pos(self, probe_position: spec_pb2.ProbePosition
                         ) -> control_pb2.ControlResponse:
        """Override for proper pos moving."""
        rep = super().on_set_probe_pos(probe_position)
        if rep == control_pb2.ControlResponse.REP_SUCCESS:
            self._start_probe_pos_move()
            self._probe_pos_moving = True
        return rep

    # --- Feedback stuff --- #
    def switch_feedback_mode(self, mode: params.FeedbackMode):
        """Switch to using appropriate feedback mode."""
        self.param_handler.switch_feedback_mode(mode)

    # --- Spectroscopy Setters --- #
    def set_spectroscopy_mode(self, spec_mode: params.SpectroscopyMode):
        """Switch spectroscopy to chosen mode."""
        self.param_handler.set_param(params.SXMParam.SPEC_MODE,
                                     spec_mode.value)

    def set_spectroscopy_settings(self,
                                  settings: params.SpectroscopySettingsHeight |
                                  params.SpectroscopySettingsBias):
        """Set spectroscopy settings for D(z) or D(U).

        We currently only support setting one of these two modes. Its main use
        is to configure the 'fake' spectroscopy we use to move the probe pos.

        Note that after setting, we return the spectroscopy mode to
        self._spectroscopy_mode.
        """
        mode = get_spectroscopy_mode(settings)
        self.param_handler.set_param(params.SXMParam.SPEC_MODE, mode.value)
        for uuid, val in zip(settings.get_uuids(), astuple(settings)):
            self.param_handler.set_param(uuid, val)

    # --- Spectroscopy callback --- #
    def _register_scan_spec_end_callbacks(self, client: sxm.DDEClient):
        """Ensure we detect when scans/specs end, to update scope state."""
        client.register_spect_save_callback(self._on_spec_end)

    def _on_spec_end(self, filename: str):
        """Return scope state to free when spec ends.

        The main scope state logic is handled in on_action_request()
        and on_spec_end().

        On a spectroscopy ending, we call _handle_probe_pos_move() if
        it was a 'fake' spectroscopy to move the probe.
        """
        self.scope_state = scan_pb2.ScopeState.SS_FREE

        # Force update specs and send scope state (setting above
        # means the logic in _handle_polling_device will not detect
        # a change, so we have to force it).
        self._update_specs()
        self._force_send_scope_state(self.scope_state)

        if self._probe_pos_moving:
            self._delete_fake_spec(filename)
            self._end_probe_pos_move()
            self._probe_pos_moving = False
        # Force one more loop to grab ACK from start_spec() (send after
        # the spec_end callback).
        sxm.loop()

    # --- Probe Pos Movement Faking --- #
    def _start_probe_pos_move(self):
        """Start a probe movement.

        The SXM controller does not move the probe position on set.
        In fact, the recommended way to move the probe is to force a
        spectroscopy!

        This method does that, which means we have to:
        - We change to our 'fake spect' self._fake_spectroscopy_mode.
        - Run spect.

        Note that separately we will delete this fake spect once it
        finishes. We cannot disable saving because the only way
        we know a spectroscopy ends is due to it saving.
        """
        mode = get_spectroscopy_mode(self._fake_spectroscopy_settings)
        self.param_handler.set_param(params.SXMParam.SPEC_MODE,
                                     mode.value)
        self.action_handler.request_action(MicroscopeAction.START_SPEC)

    def _end_probe_pos_move(self):
        """End a probe pose movement.

        Here, we:
        - Switch to the prior spect mode.
        """
        self.param_handler.set_param(params.SXMParam.SPEC_MODE,
                                     self._spectroscopy_mode)
        self._prior_spec_mode = None
        self._prior_spec_vals = None

    def _delete_fake_spec(self, filename: str):
        """Delete the file we created to move the probe position."""
        latest_dir = self._client.get_ini_entry(self.INI_SECTION_SAVE,
                                                self.INI_ITEM_PATH)
        spec_path = os.path.join(latest_dir, filename)
        if os.path.isfile(spec_path):
            os.remove(spec_path)


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


def get_spectroscopy_mode(settings: params.SpectroscopySettingsHeight |
                          params.SpectroscopySettingsBias):
    """Get the spec mode associated with given settings.

    Note we only support D(z) or D(U) right now.
    """
    if isinstance(settings, params.SpectroscopySettingsHeight):
        mode = params.SpectroscopyMode.X_Z.value
    elif isinstance(settings, params.SpectroscopySettingsBias):
        mode = params.SpectroscopyMode.X_Z.value
    else:
        msg = 'Unable to set spectroscopy settings for unsupported mode.'
        raise MicroscopeError(msg)
