"""Holds logic for performing actions with the Nanonis controller."""

import logging

from afspm.components.microscope import actions

from .client import NanonisClient
from .message import base, scan, spectroscopy


logger = logging.getLogger(__name__)


class NanonisActionHandler(actions.ActionHandler):
    """Implements Nanonis-specific action handling.

    Attributes:
        _client: TCP client used to communicate with Nanonis.
        _guid_to_reqrep_map: mapping from general action ID to
            request-reply structures.
    """

    def __init__(self, client: NanonisClient,
                 mode: spectroscopy.SpectroscopyMode,
                 **kwargs):
        """Set up spectroscopy mode."""
        self._client = client
        self._switch_spectroscopy_mode(mode)

        self._guid_to_reqrep_map = {}
        self._populate_guid_to_reqrep_map()

    def _populate_guid_to_reqrep_map(self):
        self._guid_to_reqrep_map[actions.MicroscopeAction.START_SCAN] = (
            base.NanonisReqRep(scan.ScanActionReq(), scan.ScanActionRep()))
        self._guid_to_reqrep_map[actions.MicroscopeAction.STOP_SCAN] = (
            self._guid_to_reqrep_map[actions.MicroscopeAction.START_SCAN])

        self._update_spec_mappings()

    def _update_spec_mappings(self, mode: spectroscopy.SpectroscopyMode):
        """Update mappings for spectroscopy actions based on current mode."""
        if mode == spectroscopy.SpectroscopyMode.BIAS:
            start_req = spectroscopy.BiasSpectraStartReq()
            start_rep = spectroscopy.BiasSpectraStartRep()
            stop_req = spectroscopy.BiasSpectraStopReq()
            stop_rep = spectroscopy.BiasSpectraStopRep()
        else:
            start_req = spectroscopy.ZSpectraStartReq()
            start_rep = spectroscopy.ZSpectraStartRep()
            stop_req = spectroscopy.ZSpectraStopReq()
            stop_rep = spectroscopy.ZSpectraStopRep()

        self._guid_to_reqrep_map[actions.MicroscopeAction.START_SPEC] = (
            base.NanonisReqRep(start_req, start_rep))
        self._guid_to_reqrep_map[actions.MicroscopeAction.STOP_SCAN] = (
            base.NanonisReqRep(stop_req, stop_rep))

    def set_spectroscopy_mode(self, mode: spectroscopy.SpectroscopyMode):
        """Switch to using the appropriate spectroscopy mode."""
        self._update_spec_mappings(mode)

    def _call_action(self, guid: str) -> base.NanonisResponse | None:
        """Mimics _get_param_spm_struct method in params.py."""
        try:
            req_rep = self._guid_to_reqrep_map[guid]
        except KeyError:
            msg = f'Could not find NanonisMessages for {guid}.'
            logger.error(msg)
            raise actions.ActionConfigurationError(msg)

        requested_response = req_rep.req.request_response()
        req_buffer = base.to_bytes(req_rep.req)
        rep_buffer = self._client.send_request(req_buffer, requested_response)

        if requested_response:
            # We ensure we are able to parse the response if its a call
            # that expects one. In reality, we are just making sure there
            # is no error in the parsing (handled in the called class).
            # We do not care about what the method returns here.
            base.from_bytes(rep_buffer, req_rep.rep,
                            requested_response)


def scan_action(handler: NanonisActionHandler,
                action: scan.ScanAction):
    """Start/stop scan."""
    guid = (actions.MicroscopeAction.START_SCAN
            if action == scan.ScanAction.START
            else actions.MicroscopeAction.STOP_SCAN)
    handler._call_action(guid)


def spec_action(handler: NanonisActionHandler,
                action: scan.ScanAction):
    """Start/stop spec."""
    guid = (actions.MicroscopeAction.START_SPEC
            if action == scan.ScanAction.START
            else actions.MicroscopeAction.STOP_SPEC)
    handler._call_action(guid)
