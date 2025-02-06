"""Holds Abstract Microscope Translator Class (defines translator logic)."""

import os
import logging
import datetime
import copy
from abc import ABCMeta, abstractmethod
from typing import Callable
from types import MappingProxyType
import zmq
from google.protobuf.message import Message

from .. import component as afspmc

from ...io import common
from ...io.pubsub import publisher as pub
from ...io.pubsub import subscriber as sub
from ...io.control import server as ctrl_srvr

from ...io.protos.generated import scan_pb2
from ...io.protos.generated import control_pb2
from ...io.protos.generated import feedback_pb2


logger = logging.getLogger(__name__)


# Protos attributes we check for
TIMESTAMP_ATTRIB = 'timestamp'
ANGLE_ATTRIB = 'angle'
PARAM_VALUE_ATTRIB = 'value'

WARNING_SENT_COUNT = 0  # To ensure we don't spam about Scan2d angle issue


class MicroscopeError(Exception):
    """General MicroscopeTranslator error."""

    pass


class MicroscopeTranslator(afspmc.AfspmComponentBase, metaclass=ABCMeta):
    """Handles communicating with SPM device and handling requests.

    The MicroscopeTranslator is the principal node for communicating with an SPM
    device (usually via an actual SPM controller). It is responsible for:
    - Receiving requests from a ControlClient and responding to them;
    - Sending appropriate requests to the device itself, to perform actions;
    - Monitoring the SPM device for state changes, and reporting these changes
    to any listeners via its publisher;
    - Sending out any performed scans out to listeners via its Publisher.

    It communicates with any ControlClients via a zmq REP node, where it
    receives requests and handles them via its appropriate methods (e.g.
    on_start_scan()).

    It sends out state changes and scans via a zmq PUB node, where it publishes
    these aspects.

    This is an abstract class, as device communication is SPM controller
    specific. We expect a MicroscopeTranslator child class for a given SPM
    controller.

    Note: we allow providing a subscriber to MicroscopeTranslator (it inherits
    from AspmComponent). If subscribed to the PubSubCache, it will receive
    kill signals and shutdown appropriately.

    ---
    The MicroscopeTranslator is based around the process of setting scan
    parameters, starting and stopping scans. For many experiments, this
    may be all that is needed! This assumes the researcher has already
    approached their surface and set the necessary operating mode /
    parameters for a scan to run.

    However, it may also be necessary to:
    1. Set different parameters between scans (e.g. scan speed, feedback
    PI/PID system parameters).
    2. Switch operating modes between scans (e.g. dynamic AM-AFM mode, static
    mode with constant height).
    3. Explicitly approach/retract the tip, and use a coarse motor to move
    the scan region further around the surface.
    4. Perform tip conditioning, by moving the tip and performing one of a set
    of operations with the surface.
    5. Perform a 3D form of scanning (e.g. spectroscopy).

    For (1), we have introduced the REQ_PARAM request. The idea is to
    map settings to a common 'dictionary', with IDs defined in params.py. To
    set/get a particular parameter, the translator calls self.param_method_map
    (see ParamMethod at end of file). If a parameter ID is not in these
    maps, it is not supported.

    (2) will be introduced in the future, via a new REQ_OP_MODE call.
    Setting/getting an operating mode is the same as setting any other
    parameter! We make no special checks; it is assumed that an operating mode
    corresponds to (a) a feedback/z-controller configuration, and (b) a
    specific set of scan channels being recorded per scan (e.g. topography,
    phase). Thus, we expect setting a given operating mode ID on two different
    microscope translators to result in the same output channels per scan. Again,
    NO SPECIAL CHECKS ARE DONE: caveat emptor.

    If setting a param is not immediate (i.e. takes time), you can set
    self.scope_state to SS_BUSY_PARAM *within* the method. If doing so, you will
    need to set it to SS_FREE once ready.

    For (3)-(5): these *ARE NOT YET SUPPORTED*. We plan to introduce some
    mechanism to run actions (REQ_RUN_ACTION), to support some or all
    of these.
    ---

    Attributes:
        publisher: Publisher instance, for publishing data.
        control_server: ControlServer instance, for responding to control
            requests.
        req_handler_map: mapping from ControlRequest to method to call, for
            ease of use within some of the methods.
        scope_state: device's current ScopeState.
        scan_params; device's current ScanParameters2d.
        scan: device's most recent Scan2d.
        subscriber: optional subscriber, to hook into (and detect) kill
            signals.

        param_method_map: a mapping from param id to a method which handles
            set/get of that parameter. The method should accept an optional
            str input, corresponding to the 'set' value. If none is provided,
            only a 'get' is requested. We expect a (REP, str) as return val.
    """

    # Indicates commands we will allow to be sent while not free
    ALLOWED_COMMANDS_WHILE_NOT_FREE = [control_pb2.ControlRequest.REQ_STOP_SCAN]


    def __init__(self, name: str, publisher: pub.Publisher,
                 control_server: ctrl_srvr.ControlServer,
                 loop_sleep_s: int = common.LOOP_SLEEP_S,
                 beat_period_s: float = common.HEARTBEAT_PERIOD_S,
                 ctx: zmq.Context = None, subscriber: sub.Subscriber = None):
        """Initializes the translator.

        Args:
            name: component name.
            publisher: Publisher instance, for publishing data.
            control_server: ControlServer instance, for responding to control
                requests.
            loop_sleep_s: how long we sleep in our main loop, in s.
            beat_period_s: how frequently we should send a hearbeat.
            ctx: zmq Context; if not provided, we will create a new instance.
            subscriber: optional subscriber, to hook into (and detect) kill
                signals.
        """
        if not ctx:
            ctx = zmq.Context.instance()

        self.publisher = publisher
        self.control_server = control_server
        self.req_handler_map = self.create_req_handler_map()

        # Init our current understanding of state / params
        self.scope_state = scan_pb2.ScopeState.SS_UNDEFINED
        self.scan_params = scan_pb2.ScanParameters2d()
        self.scans = []

        self.zctrl_params = feedback_pb2.ZCtrlParameters()

        self.param_method_map = {}

        # AfspmComponent constructor: no control_client provided, as that
        # logic is handled by the control_server.
        super().__init__(name, subscriber=subscriber, control_client=None,
                         ctx=ctx, loop_sleep_s=loop_sleep_s,
                         beat_period_s=beat_period_s)

    def create_req_handler_map(self) -> dict[control_pb2.ControlRequest,
                                             Callable]:
        """Create our req_handler_map, for mapping REQ to methods."""
        return MappingProxyType({
            control_pb2.ControlRequest.REQ_START_SCAN: self.on_start_scan,
            control_pb2.ControlRequest.REQ_STOP_SCAN:  self.on_stop_scan,
            control_pb2.ControlRequest.REQ_SET_SCAN_PARAMS:
                self.on_set_scan_params,
            control_pb2.ControlRequest.REQ_SET_ZCTRL_PARAMS:
                self.on_set_zctrl_params,
            control_pb2.ControlRequest.REQ_PARAM: self._handle_param_request,
        })

    @abstractmethod
    def on_start_scan(self) -> control_pb2.ControlResponse:
        """Handle a request to start a scan."""

    @abstractmethod
    def on_stop_scan(self) -> control_pb2.ControlResponse:
        """Handle a request to stop a scan."""

    @abstractmethod
    def on_set_scan_params(self, scan_params: scan_pb2.ScanParameters2d
                           ) -> control_pb2.ControlResponse:
        """Handle a request to change the scan parameters."""

    @abstractmethod
    def on_set_zctrl_params(self, zctrl_params: feedback_pb2.ZCtrlParameters
                            ) -> control_pb2.ControlResponse:
        """Handle a request to change the Z-Controller Feedback parameters.

        If not supported, return REP_CMD_NOT_SUPPORTED.
        """

    @abstractmethod
    def poll_scope_state(self) -> scan_pb2.ScopeState:
        """Poll the translator for the current scope state.

        Throw MicroscopeError on failure.
        """

    @abstractmethod
    def poll_scan_params(self) -> scan_pb2.ScanParameters2d:
        """Poll the controller for the current scan parameters.

        Throw MicroscopeError on failure.
        """

    @abstractmethod
    def poll_zctrl_params(self) -> feedback_pb2.ZCtrlParameters:
        """Poll the controller for the current Z-Control parameters.

        If not supported, return a new ZCtrlParameters instance:
            return feedback_pb2.ZCtrlParameters()

        Throw MicroscopeError on failure.
        """

    @abstractmethod
    def poll_scans(self) -> list[scan_pb2.Scan2d]:
        """Obtain latest performed scans.

        We will compare the prior scans (or first of each) to the latest to
        determine if the scan succeeded (i.e. they are different). Note that
        each channel is a different scan! Thus, when we say 'latest scans',
        we really mean the latest single- or multi-channel scan, provided as
        a list of Scan2ds (with each Scan2d being a channel of the scan).

        Note that we will first consider the timestamp attribute when
        comparing scans. If this attribute is not passed, we will do
        a data comparison.

        Throw MicroscopeError on failure.

        To read the creation time of a file using Python, use
            get_file_modification_datetime()
        and you can put that in the timestamp param with:
            scan.timestamp.FromDatetime(ts)
        """

    def _handle_polling_device(self):
        """Poll aspects of device, and publishes changes (including scans).

        Note: we expect scope state to be sent *last*, so that any client has
        the ability to validate the expected changes have taken effect. Put
        differently: any client should get all other changes *before* the
        state change.
        """
        old_scope_state = copy.deepcopy(self.scope_state)
        self.scope_state = self.poll_scope_state()

        if (old_scope_state == scan_pb2.ScopeState.SS_COLLECTING and
                self.scope_state != scan_pb2.ScopeState.SS_COLLECTING):
            old_scans = copy.deepcopy(self.scans)
            self.scans = self.poll_scans()

            # If scans are different, assume new and send out!
            # Test timestamps if they exist. Otherwise, compare
            # data arrays.
            send_scan = False

            both_have_scans = len(self.scans) > 0 and len(old_scans) > 0
            only_new_has_scans = (len(self.scans) > 0 and
                                  len(old_scans) == 0)
            both_have_timestamps = both_have_scans and (
                self.scans[0].HasField(TIMESTAMP_ATTRIB) and
                old_scans[0].HasField(TIMESTAMP_ATTRIB))

            # First, check if timestamps are different
            scans_different = both_have_timestamps and (
                self.scans[0].timestamp != old_scans[0].timestamp)
            # Only compare scan data if not the case.
            scans_different = scans_different or both_have_scans and (
                self.scans[0].values != old_scans[0].values)

            if only_new_has_scans or scans_different:
                send_scan = True

            if send_scan:
                logger.info("New scans, sending out.")
                _check_and_warn_angle_issue(self.scans)
                for scan in self.scans:
                    self.publisher.send_msg(scan)

        old_scan_params = copy.deepcopy(self.scan_params)
        self.scan_params = self.poll_scan_params()
        if old_scan_params != self.scan_params:
            logger.info("New scan_params, sending out.")
            self.publisher.send_msg(self.scan_params)

        old_zctrl_params = copy.deepcopy(self.zctrl_params)
        self.zctrl_params = self.poll_zctrl_params()
        if old_zctrl_params != self.zctrl_params:
            logger.info("New zctrl_params, sending out.")
            self.publisher.send_msg(self.zctrl_params)

        # scope state changes sent *last*!
        if old_scope_state != self.scope_state:
            logger.info("New scope state %s, sending out.",
                        common.get_enum_str(scan_pb2.ScopeState,
                                            self.scope_state))
            scope_state_msg = scan_pb2.ScopeStateMsg(
                scope_state=self.scope_state)
            self.publisher.send_msg(scope_state_msg)

    def _handle_incoming_requests(self):
        """Poll control_server for requests and responds to them."""
        req, proto = self.control_server.poll()
        if req:  # Ensure we received something
            # Refuse most requests while moving/scanning (not free)
            if (self.scope_state != scan_pb2.ScopeState.SS_FREE and
                    req not in self.ALLOWED_COMMANDS_WHILE_NOT_FREE):
                self.control_server.reply(
                    control_pb2.ControlResponse.REP_NOT_FREE)
            else:
                handler = self.req_handler_map[req]
                rep = handler(proto) if proto else handler()

                # Special case! If scan was cancelled successfully, we
                # send out an SS_INTERRUPTED state, to allow detecting
                # interruptions.
                if (req == control_pb2.ControlRequest.REQ_STOP_SCAN and
                        rep == control_pb2.ControlResponse.REP_SUCCESS):
                    scope_state_msg = scan_pb2.ScopeStateMsg(
                        scope_state=scan_pb2.ScopeState.SS_INTERRUPTED)
                    logger.info("Scan interrupted, sending out %s.",
                                common.get_enum_str(scan_pb2.ScopeState,
                                                    scope_state_msg.scope_state))
                    self.publisher.send_msg(scope_state_msg)

                if isinstance(rep, tuple):  # Special case of rep with obj
                    self.control_server.reply(rep[0], rep[1])
                else:
                    self.control_server.reply(rep)

    def _handle_param_request(self, param: control_pb2.ParameterMsg
                              ) -> (control_pb2.ControlResponse,
                                    Message | int | None):
        """Set or get a device parameter.

        Respond to a ParameterMsg request. This method depends entirely on the
        param_method_map, which maps set/get methods to given parameters.

        Note: if a parameter SET is requested which induces some delay, change
        self.scope_state to SS_BUSY_PARAM within the associated set method, and
        ensure it is updated in poll_scope_state() once ready. This class does
        no special checks for this state, so be careful not to cause your
        translator to get stuck in this state!

        Args:
            param: ParameterMsg request; if value is not provided, treated as
                a 'get' request. Otherwise, treated as a 'set' request.

        Returns:
            - Response to the request.
            - A ParameterMsg response, indicating the state after the set (or
                just the state, if it was a get call).
        """
        if (param.parameter not in self.param_method_map):
            return (control_pb2.ControlResponse.REP_PARAM_NOT_SUPPORTED,
                    param)

        if param.HasField(PARAM_VALUE_ATTRIB):
            rep, val, units = self.param_method_map[param.parameter](
                self, param.value, param.units)
        else:
            rep, val, units = self.param_method_map[param.parameter](self)

        if val:
            param.value = val
            param.units = units
        return (rep, param)

    def run_per_loop(self):
        """Where we monitor for requests and publish results."""
        self._handle_incoming_requests()
        self._handle_polling_device()


def _check_and_warn_angle_issue(scans: [scan_pb2.Scan2d]):
    """Check if the angle parameter was not set. Warn user if so."""
    global WARNING_SENT_COUNT
    if (len(scans) > 0 and
            not scans[0].params.spatial.roi.HasField(ANGLE_ATTRIB) and
            WARNING_SENT_COUNT == 0):
        logger.warning('Scans received without ROI angle set. If angles '
                       'were used during collection, this can cause issues '
                       'when comparing scan data. Update your translator to '
                       'set this attribute.')
        WARNING_SENT_COUNT += 1


def get_file_modification_datetime(filename: str) -> datetime.datetime:
    """Read modification time of a file, return a datetime representing it.

    Taken from: https://stackoverflow.com/questions/237079/how-do-i-get-file-
    creation-and-modification-date-times.
    """
    return datetime.datetime.fromtimestamp(os.path.getmtime(filename),
                                           tz=datetime.timezone.utc)


# Description of method for MicroscopeTranslator.param_method_map).
#
# This method takes in the translator, an optional set_value (if setting), and
# an optional units str (required if are set_value is provided).
# It returns (ControlResponse, get_value, units) of the operation. Passing the
# translator allows using internal variables that may be needed/desired.
#
# Your ParamMethod is responsible for converting the received value to your
# internal reference units, if not the same (see utils/units.py). In the same
# fashion, the component that made this request is responsible for converting
# the *received* value into *its own* reference units. See
# docs/design_philosphy.md for more info.
#
# NOTE: The input and output params are str!
ParamMethod = Callable[[MicroscopeTranslator, str | None, str | None],
                       tuple[control_pb2.ControlResponse, str, str]]
