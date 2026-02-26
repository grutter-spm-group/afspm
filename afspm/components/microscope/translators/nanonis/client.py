"""Client for communicating with Nanonis controller."""

import socket
import logging

from .message import base


logger = logging.getLogger(__name__)


# TODO: Review these defaults!
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 6501
DEFAULT_TIMEOUT_S = 5.0
DEFAULT_BUFSIZE = 1024


class NanonisCommunicationError(Exception):
    """Something went amuck sending requests and getting responses."""


class NanonisClient:
    """TCP Client to communicate with Nanonis Controller.

    The NanonisClient will create a TCP connection with the Nanonis controller
    given a provided host and port.

    Attributes:
        _host: url address of server we are connecting to.
        _port: port number of server we are connecting to.
        _timeout_s: how long to wait for a response from server. Defaults to
            DEFAULT_TIMEOUT_S.
        _bufsize: max size of response we expect. Defaults to DEFAULT_BUFSIZE.
    """

    def __init__(self, host: str = DEFAULT_HOST,
                 port: int = DEFAULT_PORT,
                 timeout_s: float = DEFAULT_TIMEOUT_S,
                 bufsize: int = DEFAULT_BUFSIZE):
        """Init client."""
        self._host = host
        self._port = port
        self._timeout_s = timeout_s
        self._bufsize = bufsize

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Connect
        self._socket.settimeout(self._timeout_s)
        self._socket.connect((self._host, self._port))

    def send_request(self, buffer: bytes,
                     expect_response: bool) -> bytes | None:
        """Send a request to NanonisClient, receive optional response.

        Args:
            buffer: request in a bytes array.
            expect_response: whether or not we expect a response.

        Returns:
            response, as a bytes array, or None if expect_response is False.

        Raises:
            - TimeoutError if we did not receive an acknowledgement of our
            request or a response (if expected) within self._timeout_s.
            - NanonisMessageError if we received a response but it indicates
            an error.
        """
        try:
            self._socket.sendall(buffer)
        except TimeoutError as e:
            logger.error('Timeout error sending request.')
            raise e

        response = None
        if expect_response:
            try:
                response = self._socket.recv(self._bufsize)
            except TimeoutError as e:
                logger.error('Timeout error receiving response from request.')
                raise e
        return response


def send_request(client: NanonisClient, req: base.NanonisRequest,
                 rep: base.NanonisResponse | None
                 ) -> base.NanonisResponse | None:
    """Send a request and receive a response (if expected).

    This is effectively a wrapper around NanonisClient.send_request(),
    where we pack our NanonisRequest before sending and unpack our
    NanonisResponse on receipt (if applicable). If rep is None, we
    do not expect a response.

    Args:
        client: NanonisClient used to send our request and receive a reply.
        req: NanonisRequest we wish to send.
        rep: NanonisResponse type we expect. If None, we do not expect to
            receive a response.

    Returns:
        NanonisResponse of type rep that has been populated with received data,
            or None if no rep was provided.
    """
    logger.trace(f'Sending request: {req}')
    logger.trace(f'Requesting response: {rep is not None}')
    req_buffer = base.to_bytes(req)
    rep_buffer = client.send_request(req_buffer, rep is not None)
    logger.trace(f'Received response: {rep}')

    if rep:
        if not rep_buffer:
            msg = (f'Expected response for {req.get_command_name()},'
                   ' but got none.')
            logger.error(msg)
            raise NanonisCommunicationError(msg)  # TODO: Catch in params/actions

        rep = base.from_bytes(rep_buffer, rep)
    return rep
