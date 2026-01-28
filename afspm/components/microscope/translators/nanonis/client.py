"""Client for communicating with Nanonis controller."""

import socket
import logging


logger = logging.getLogger(__name__)


# TODO: Review these defaults!
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 6501
DEFAULT_TIMEOUT_S = 5.0
DEFAULT_BUFSIZE = 1024


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
