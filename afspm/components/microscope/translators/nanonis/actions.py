"""Holds logic for performing actions with the Nanonis controller."""

import logging

from afspm.components.microscope import actions

from . import client as clnt
from .message import base, scan, spectroscopy


logger = logging.getLogger(__name__)


class NanonisActionHandler(actions.ActionHandler):
    """Implements Nanonis-specific action handling.

    Attributes:
        _client: TCP client used to communicate with Nanonis.
        _guid_to_reqrep_map: mapping from general action ID to
            request-reply structures.
    """

    def __init__(self, client: clnt.NanonisClient, **kwargs):
        """Set up spectroscopy mode."""
        self._client = client
        self._guid_to_reqrep_map = {}
        self._populate_guid_to_reqrep_map()

    def _populate_guid_to_reqrep_map(self):
        self._guid_to_reqrep_map[actions.MicroscopeAction.START_SCAN] = (
            base.NanonisReqRep(scan.ScanActionReq(), scan.ScanActionRep()))
        self._guid_to_reqrep_map[actions.MicroscopeAction.STOP_SCAN] = (
            self._guid_to_reqrep_map[actions.MicroscopeAction.START_SCAN])
        # Set default spectroscopy mapping
        self._update_spec_mappings(spectroscopy.SpectroscopyMode.BIAS)

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

        req = self._guid_to_reqrep_map[guid].req
        rep = (self._guid_to_reqrep_map[guid].rep if req.request_response()
               else None)
        rep = send_request(self._client, req, rep)


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


def send_request(client: clnt.NanonisClient, req: base.NanonisRequest,
                 rep: base.NanonisResponse | None
                 ) -> base.NanonisResponse | None:
    """Wrap client.py method, with Exception swapping."""
    try:
        clnt.send_request(client, req, rep)
    except clnt.NanonisCommunicationError as e:
        raise actions.ActionError(str(e))
