"""Holds logic for performing actions with the Nanonis controller."""

import logging

from afspm.components.microscope import actions

from . import client as clnt
from .message import base, scan, spectroscopy


logger = logging.getLogger(__name__)


class NanonisActionHandler(actions.ActionHandler):
    """Implements Nanonis-specific action handling.

    Note: it turns out the spec start command is always synchronous. We can
    work around this limitation by having a separate client connection just
    for spec start calls.

    Attributes:
        _client: TCP client used to communicate with Nanonis.
        _spec_start_client: TCP client used to send spec start calls,
            since it is synchronous and thus breaks other polls.
        _scan_direction: holds the latest direction we will use when
            sending the request out.
        _spectroscopy_mode: the mode of spectroscopy we use for our specs.
    """

    def __init__(self, client: clnt.NanonisClient,
                 spec_start_port: int = clnt.DEFAULT_SPEC_START_PORT,
                 **kwargs):
        """Set up spectroscopy mode."""
        self._client = client
        self._spec_start_client = clnt.NanonisClient(
            client._host, spec_start_port, client._timeout_s,
            client._bufsize)
        self._scan_direction = 0
        self._spectroscopy_mode = spectroscopy.SpectroscopyMode.BIAS
        super().__init__(**kwargs)

    def set_spectroscopy_mode(self, mode: spectroscopy.SpectroscopyMode):
        """Switch to using the appropriate spectroscopy mode."""
        self._spectroscopy_mode = mode


def scan_action(handler: NanonisActionHandler,
                action: int):
    """Start/stop scan."""
    action = scan.ScanAction(action)  # Validate the number is valid
    req = scan.ScanActionReq(action=action.value,  # Convert to int again
                             direction=handler._scan_direction % 2)
    handler._scan_direction += 1  # Increment to change direction
    rep = scan.ScanActionRep()

    send_request(handler._client, req, rep if req.request_response()
                 else None)


def spec_action(handler: NanonisActionHandler,
                action: int):
    """Start/stop spec."""
    action = scan.ScanAction(action)  # Validate the number is valid

    if action == scan.ScanAction.START:
        client = handler._spec_start_client
        if handler._spectroscopy_mode == spectroscopy.SpectroscopyMode.Z:
            req = spectroscopy.ZSpectraStartReq()
            rep = spectroscopy.ZSpectraStartRep()
        else:
            req = spectroscopy.BiasSpectraStartReq()
            rep = spectroscopy.BiasSpectraStartRep()
    else:
        client = handler._client
        if handler._spectroscopy_mode == spectroscopy.SpectroscopyMode.Z:
            req = spectroscopy.ZSpectraStopReq()
            rep = spectroscopy.ZSpectraStopRep()
        else:
            req = spectroscopy.BiasSpectraStopReq()
            rep = spectroscopy.BiasSpectraStopRep()

    send_request(client, req, rep if req.request_response() else None)


def send_request(client: clnt.NanonisClient, req: base.NanonisRequest,
                 rep: base.NanonisResponse | None
                 ) -> base.NanonisResponse | None:
    """Wrap client.py method, with Exception swapping."""
    try:
        return clnt.send_request(client, req, rep)
    except clnt.NanonisCommunicationError as e:
        raise actions.ActionError(str(e))
