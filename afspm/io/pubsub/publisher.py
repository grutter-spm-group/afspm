"""Holds our Publisher logic."""

from typing import Callable
import logging

import zmq

from google.protobuf.message import Message
from google.protobuf.timestamp_pb2 import Timestamp

from .. import common
from . import defaults


logger = logging.getLogger(__name__)


def create_message_packet(env: str, proto: Message, ts: Timestamp):
    """Create publishing message packet.

    We convert a message packet into a list of bytes objects.
    """
    return [env.encode(),
            proto.SerializeToString(),
            ts.SerializeToString()]


class Publisher:
    """Encapsulates publisher node logic.

    More particularly, this encapsulates the proto-to-envelope mapping
    (get_envelope_for_proto), so the method using it can simply feed the
    desired proto.

    Attributes:
        _publisher: the zmq PUB socket for sending messages out.
        _get_envelope_for_proto: method that maps from proto message to
            our desired publisher 'envelope' string.
        _get_envelope_kwargs: any additional arguments to be fed to
            get_envelope_for_proto.
        _uuid: a uuid to differentiate publishers in logs.
    """

    def __init__(self, url: str,
                 get_envelope_for_proto: Callable[[Message], str] =
                 defaults.PUBLISHER_ENVELOPE_FOR_PROTO,
                 ctx: zmq.Context = None,
                 get_envelope_kwargs: dict =
                 defaults.PUBLISHER_ENVELOPE_KWARGS,
                 uuid: str = None):
        """Initialize the publisher.

        Args:
            url: our publishing address, in zmq format.
            get_envelope_for_proto: method that maps from proto message to
                our desired publisher 'envelope' string.
            ctx: zmq Context; if not provided, we will create a new instance.
            get_envelope_kwargs: any additional arguments to be fed to
                get_envelope_for_proto.
            uuid: uuid, to be used to differentiate in logs.
        """
        self._get_envelope_for_proto = get_envelope_for_proto
        self._get_envelope_kwargs = (get_envelope_kwargs if get_envelope_kwargs
                                     else {})
        self._uuid = uuid

        if not ctx:
            ctx = zmq.Context.instance()

        self._publisher = ctx.socket(zmq.PUB)
        self._publisher.setsockopt(zmq.LINGER, 0)  # Never linger on closure
        self._publisher.bind(url)

        common.sleep_on_socket_startup()

    def send_message(self, proto: Message, ts: Timestamp):
        """Send message via publisher.

        It uses get_envelope_for_proto to determine the envelope of our
        message.

        --- NOTE ---
        We purposefully force the user to provide a timestamp, to avoid
        potential cache issues. If this message is completely original (e.g.
        it came from the MicroscopeTranslator, it should use common.create_ts()
        to create a new timestamp.

        If, however, it is *derived* from prior data, it should use the
        timestamp of that data! In doing so, we can ensure that 'old' data
        does not get re-read by components if a new component is spawned.
        This is because the new component will receive all old messages
        in the cache and respond. Any data derived from data in the cache
        should have the original data's timestamp, so it is automatically
        treated as old and disregarded by pre-existing components.

        Args:
            proto: protobuf message to send.
            ts: timestamp for said message.
        """
        envelope = self._get_envelope_for_proto(proto,
                                                **self._get_envelope_kwargs)
        logger.debug(f"{self._uuid}: Sending message {envelope}")
        self._publisher.send_multipart(
                    create_message_packet(envelope, proto, ts))

    def send_kill_signal(self):
        """Send a kill signal to subscribers."""
        logger.debug(f"{self._uuid}: Sending kill signal.")
        self._publisher.send_multipart([common.KILL_SIGNAL.encode()])

    def set_uuid(self, uuid: str):
        """Set id, to differentiate when logging."""
        self._uuid = uuid
