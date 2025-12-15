"""Handles device communication with the Omicron SXM controller.

The directory containing SXMRemote must be added to pythonpath of venv
TODO do this ourselves with the poetry setup files?
say this in readme
"""

import logging
import os
from glob import glob

from SciFiReaders.readers.microscopy.spm.afm import pifm

from ...params import (ParameterHandler,
                       DEFAULT_PARAMS_FILENAME)
from ...actions import (ActionHandler,
                        DEFAULT_ACTIONS_FILENAME)
from ... import config_translator as ct

from .....utils import array_converters as conv

from .....io.protos.generated import scan_pb2
from .....io.protos.generated import spec_pb2
from .....io.protos.generated import control_pb2

from . import params
from . import actions


logger = logging.getLogger(__name__)


# Import SXMRemote (main SXM interface), and throw error on failure.
try:
    import SXMRemote
except ModuleNotFoundError as e:
    logger.error("SXMRemote not found, make sure to add it to your PythonPath:"
                 '\n\t Export PYHTONPATH = < PathToSXMRemote >:$PYTHONPATH"')
    raise e


logger = logging.getLogger(__name__)


class SXMTranslator(ct.ConfigTranslator):
    """Handles device communication with the Scienta Omicron SXM controller.

    The SXMTranslator communicates with the Asylum Research software via the
    XopClient, which sends/receives JSON messages over a zmq interface as
    defined by the Allen Institute's ZeroMQ-XOP project:
    https://github.com/AllenInstitute/ZeroMQ-XOP

    Note: we encountered difficulties working with the methods provided by
    Anfatec to read the latest scan, so we request the directory where scans
    are saved via the constructor to find the latest one ourselves.

    Attributes:
        _old_scans: the last scans, to send out if it has not changed.
        _old_scan_path: the prior scan filepath. We use this to avoid loading
            the same scans multiple times.
        _old_spec: the last spec, to send out if it has not changed.
        _old_spec_path: the prior spec filepath. We use this to avoid loading
            the same spectroscopies multiple times.
        _client: DDE Client used to interact with SXM.
        _save_dir: directory where we expect to find our scans/specs. I suppose
            it cannot be queried from SXM :( ?
    """

    def __init__(self, param_handler: ParameterHandler = None,
                 action_handler: ActionHandler = None,
                 client: SXMRemote.DDEClient = None,
                 save_dir: str = None,
                 **kwargs):
        """Init our translator."""
        self._old_scan_path = None
        self._old_scans = []
        self._old_spec_path = None
        self._old_spec = None
        self._save_dir = save_dir

        # Default initialization of handler
        kwargs = self._init_handlers(client, param_handler, action_handler,
                                     **kwargs)
        # Tell parent class that SXM *does not* detect moving
        kwargs[ct.DETECTS_MOVING_KEY] = False
        super().__init__(**kwargs)
        self._init_spec_settings()

    def _init_handlers(self, client: SXMRemote.DDEClient,
                       param_handler: ParameterHandler,
                       action_handler: ActionHandler,
                       **kwargs) -> dict:
        """Init handlers and update kwargs."""
        if not client:
            client = SXMRemote.DDEClient("SXM", "Remote")
        if not param_handler:
            param_handler = _init_param_handler(client)
            kwargs[ct.PARAM_HANDLER_KEY] = param_handler
        if not action_handler:
            action_handler = _init_action_handler(client)
            kwargs[ct.ACTION_HANDLER_KEY] = action_handler
        return kwargs

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
        state = self.param_handler.get_param(params.SXMParam.SCAN_STATE)

        if state == 1:
            return scan_pb2.ScopeState.SS_SCANNING
        # TODO: How to check for SS_SPEC??
        else:
            return scan_pb2.ScopeState.SS_FREE

    def _get_latest_file(self) -> str | None:
        """Return the location of the metadata for the latest scan.

        Raises:
            ValueError if the file structure is incorrect (i.e. there are
                no/several metadata files in a sub-directory).
        """
        try:
            latest_dir = max(glob(os.path.join(self._save_dir, '*/')),
                             key=os.path.getmtime)
        except ValueError:
            msg = ("No sub-directory (scans) found in main directory when "
                   "polling for latest scans/specs.")
            logger.warning(msg)
            return None

        try:
            txts = glob(os.path.join(latest_dir, "*.txt"))
            if len(txts) != 1:  # there should only be one .txt per dir.
                # TODO: check that this is actually the case
                msg = (f"Found {len(txts)} txt files in scan directory " +
                       f"{latest_dir} when there should only be one.")
                logger.error(msg)
                raise ValueError(msg)
        except ValueError:
            msg = ("No metadata text file found in the latest dir in the scan "
                   "directory")
            logger.warning(msg)
            raise ValueError(msg)
        return txts[0]  # Returning first metadata file in latest scan subdir.

    def poll_scans(self) -> [scan_pb2.Scan2d]:
        """Override polling of scans."""
        scan_path = self._get_latest_file()  # TODO: Should this be done elsewhere?

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
        spec_path = self._get_latest_file()  # TODO: Should this be done elsewhere?

        # TODO: What are specs and what are scans? How do we differentiate
        # from the folders?

        if (spec_path and not self._old_spec_path or
                spec_path != self._old_spec_path):
            spec = load_spec_from_file(spec_path)
            spec = ct.correct_spec(spec, self._latest_probe_pos)
            if spec:
                self._old_spec_path = spec_path
                self._old_spec = spec
        return self._old_spec


# TODO: Consider pulling client up to translator level if it needs resetting?
def _init_action_handler(client: SXMRemote.DDEClient
                         ) -> actions.AsylumActionHandler:
    """Initialize Asylum action handler pointing to defulat config."""
    actions_config_path = os.path.join(os.path.dirname(__file__),
                                       DEFAULT_ACTIONS_FILENAME)
    return actions.AsylumActionHandler(actions_config_path, client)


def _init_param_handler(client: SXMRemote.DDEClient
                        ) -> params.AsylumParameterHandler:
    """Initialize Asylum action handler pointing to defulat config."""
    params_config_path = os.path.join(os.path.dirname(__file__),
                                      DEFAULT_PARAMS_FILENAME)
    return params.AsylumParameterHandler(params_config_path, client)


def load_scans_from_file(scan_path: str
                         ) -> list[scan_pb2.Scan2d] | None:
    """Load SXM scan, filling in info possible from file only.

    Args:
        scan_path: path to the scan.

    Returns:
        loaded scans in scan_pb2 format (one scan per channel). None if
        dataset is empty or failure loading scan.
    """
    raise RuntimeError.NotImplementerError('write me, dummy!')


def load_spec_from_file(fname: str,
                        ) -> spec_pb2.Spec1d | None:
    """Load Spec1d from provided filename (None on failure).

    Args:
        fname: path to spec file.

    Returns:
        Spec1d if loaded properly, None if spec file was empty or exception
        thrown when reading.
    """
    raise RuntimeError.NotImplementerError('write me, dummy!')
