"""Holds our Subscriber logic."""

from typing import Callable
from collections.abc import Iterable
from abc import ABC, abstractmethod
import logging

import zmq

from google.protobuf.message import Message

from .. import common
from . import defaults


logger = logging.getLogger(__name__)


class ABCSubscriber(ABC):
    """Abstract subscriber class.

    The main accessor is poll_and_store(), by which we check a subscriber node
    for messages having been received. These are stored in the cache property.

    There is a hardcoded KILL_SIGNAL which we check for. Its state is held in
    the property shutdown_was_requested.
    """

    @abstractmethod
    def poll_and_store(self) -> list[tuple[str, Message]] | None:
        """Receive message(s) and store in cache.

        Returns:
            - A list of tuples containing the envelope key of the emessage
                and the protobuf.Message received; or
            - None, if no message received.
        """

    @property
    @abstractmethod
    def cache(self):
        """Holds messages received, in mapping type.

        We expect our cache to consist of:
        - keys that are strings, equivalent to the topics we send.
        - values that are iterables. So, even if only storing 1 object, make
        sure it is in an iterable format.
        """

    @property
    @abstractmethod
    def shutdown_was_requested(self):
        """Whether or not a kill signal has been received."""


class Subscriber(ABCSubscriber):
    """Encapsulates subscriber node logic.

    More particularly, encapsulates:
    - a topic-to-proto mapping, sub_extract_proto(), to know what protobuf
    message we have received.
    - a caching mechanism, to store the results as we receive them.

    The main accessor is poll_and_store(), though you can choose to grab the
    _subscriber socket directly for polling externally. In such a scenario,
    call _on_message_received() to handle message decoding and caching.

    Attributes:
        cache: the cache, where we store results according to update_cache.
        shutdown_was_requested: bool, indicating whether or not a kill signal
            has been received.

        _sub_extract_proto: method which extracts the proto message from a
            message received from the sub. It must therefore know the
            topic-to-proto mapping.
        _extract_proto_kwargs: any additional arguments to be fed to
            sub_extract_proto.
        _update_cache: method that updates our cache based on
            the provided 'topic' and proto.
        _update_cache_kwargs: any additional arguments to be fed to
            update_cache.
        _subscriber: the zmq SUB socket for connecting to the publisher.
        _poll_timeout_ms: the poll timeout, in milliseconds. If None,
            we do not poll and do a blocking receive instead.
        _uuid: a uuid to differentiate subscribers in logs.
    """

    def __init__(self, sub_url: str,
                 sub_extract_proto: Callable[[list[bytes]], Message] =
                 defaults.EXTRACT_PROTO,
                 topics_to_sub: list[str] = [''],
                 update_cache: Callable[[str, Message,
                                         dict[str, Iterable]],
                                        dict[str, Iterable]] =
                 defaults.UPDATE_CACHE,
                 ctx: zmq.Context = None,
                 extract_proto_kwargs: dict =
                 defaults.SUBSCRIBER_EXTRACT_PROTO_KWARGS,
                 update_cache_kwargs: dict =
                 defaults.SUBSCRIBER_UPDATE_CACHE_KWARGS,
                 poll_timeout_ms: int = common.POLL_TIMEOUT_MS,
                 uuid: str = None):
        """Initialize the caching logic and subscribes.

        Args:
            sub_url: the address of the publisher we will subscribe to, in
                zmq format.

            sub_extract_proto: method which extracts the proto message from a
                message received from the sub. It must therefore know the
                topic-to-proto mapping.
            topics_to_sub: list of topics we wish to subscribe to.
            update_cache: method that updates our cache based on
                the provided 'topic' and proto.
            ctx: zmq Context; if not provided, we will create a new
                instance.
            extract_proto_kwargs: any additional arguments to be fed to
                sub_extract_proto.
            update_cache_kwargs: any additional arguments to be fed to
                update_cache.
            poll_timeout_ms: the poll timeout, in milliseconds. If None,
                we do not poll and do a blocking receive instead.
            uuid: uuid, to be used to differentiate in logs.
        """
        self._cache = {}
        self._shutdown_was_requested = False

        self._sub_extract_proto = sub_extract_proto
        self._extract_proto_kwargs = (extract_proto_kwargs if
                                      extract_proto_kwargs else {})
        self._update_cache = update_cache
        self._update_cache_kwargs = (update_cache_kwargs if
                                     update_cache_kwargs else {})
        self._poll_timeout_ms = poll_timeout_ms
        self._uuid = uuid

        if not ctx:
            ctx = zmq.Context.instance()

        self._subscriber = ctx.socket(zmq.SUB)
        self._subscriber.connect(sub_url)

        # Subscribe to all our topics
        for topic in topics_to_sub:
            self._subscriber.setsockopt(zmq.SUBSCRIBE, topic.encode())

        # Everyone *must* subscribe to the kill signal
        self._subscriber.setsockopt(zmq.SUBSCRIBE, common.KILL_SIGNAL.encode())

        common.sleep_on_socket_startup()

    @property
    def cache(self):
        """Overload parent."""
        return self._cache

    @property
    def shutdown_was_requested(self):
        """Overload parent."""
        return self._shutdown_was_requested

    def poll_and_store(self) -> list[tuple[str, Message]] | None:
        """Receive message(s) and store in cache.

        We use a poll() first, to ensure there are messages to receive.
        If self.poll_timeout_ms is None, we do a blocking receive.

        Note: recv() *does not* handle KeyboardInterruption exceptions,
        please make sure your calling code does.

        Returns:
            - a list of tuples containing the envelope/cache key of the message
                and the protobuf.Message received; or
            - None, if no message received.
        """
        messages = []
        if self._poll_timeout_ms:
            if self._subscriber.poll(self._poll_timeout_ms, zmq.POLLIN):
                while self._subscriber.poll(0, zmq.POLLIN):
                    messages.append(self._subscriber.recv_multipart(
                        zmq.NOBLOCK))
        else:
            messages.append(self._subscriber.recv_multipart())

        decoded = []
        for msg in messages:
            dcd = self._on_message_received(msg)
            if dcd:  # Do not append None messages (KILL signals)
                decoded.append(dcd)
        return decoded if len(decoded) > 0 else None

    def _on_message_received(self, msg: list[bytes]
                             ) -> tuple[str, Message] | None:
        """Decode message and update cache.

        Args:
            msg: list of bytes corresponding to the message received by the
                frontend.

        Returns:
            a tuple containing the envelope/cache key of the message and
                the protobuf.Message received. In the case of a KILL signal,
                we return None.
        """
        envelope = msg[0].decode()
        if envelope == common.KILL_SIGNAL:
            logger.info(f"{self._uuid}: Shutdown was requested!")
            self._shutdown_was_requested = True
            return None

        proto = self._sub_extract_proto(msg, **self._extract_proto_kwargs)
        logger.debug(f"{self._uuid}: Message received {envelope}")
        self._update_cache(proto, self._cache,
                           **self._update_cache_kwargs)
        return (envelope, proto)

    def set_uuid(self, uuid: str):
        """Set id, to differentiate when logging."""
        self._uuid = uuid


class ComboSubscriber(ABCSubscriber):
    """Contains multiple subscribers."""

    def __init__(self, subs: list[Subscriber]):
        """Init combosubscriber."""
        self._subs = subs
        self._cache = {}

    def poll_and_store(self) -> list[tuple[str, Message]] | None:
        """Overload parent class."""
        self._cache = {}
        total_messages = []
        for sub in self._subs:
            sub_messages = sub.poll_and_store()
            if sub_messages:
                total_messages.extend(sub_messages)
            self._cache |= sub.cache  # Update combined cache!
        return total_messages if len(total_messages) > 0 else None

    @property
    def shutdown_was_requested(self):
        """Overload parent class."""
        shutdowns_reqd = [sub.shutdown_was_requested for sub in self._subs]
        return any(shutdowns_reqd)

    @property
    def cache(self):
        """Overload parent class."""
        return self._cache

    def set_uuid(self, uuid: str):
        """Set id, to differentiate when logging."""
        for sub in self._subs:
            sub.set_uuid(uuid)
