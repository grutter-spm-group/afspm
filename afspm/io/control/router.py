"""Holds control router, for receiving requests from different REQs."""

import copy
import zmq
import logging

from google.protobuf.message import Message

from . import commands as cmd
from .. import common

from ..protos.generated import control_pb2


logger = logging.getLogger(__name__)


class ControlRouter:
    """Encapsulates logic tied to requests from multipl ControlClients.

    The control router sits between a control server and multiple control
    clients, adding logic to decide between clients.

    Particularly:
    - Only one ControlClient can have control at a time. The logic for
        setting who is under control is within here (the client must
        request with the 'control_mode' it is currently in, and it must
        not currently be under control).
    - Any ControlClient can add or remove ExperimentProblems. If there
        are any problems in the internal list, the system cannot switch to
        ControlMode.CM_AUTOMATED.
    - All other commands are forwarded to the ControlServer *if* the client
        is under control.

    Attributes:
        shutdown_was_requested: boolean indicating whether a request to end
            the experiment has been sent.

        _ctx: Context, needed to restart the backend socket.
        _backend_url: backend url, needed to restart the backend socket.
        _backend: the REP socket that connects to the ControlServer.
        _frontend: the ROUTER socket that connects with all ControlClients.
        _problems_set: holds the set of problems which have been notified by
            ControlClients. As long as there are problems in this set, we
            cannot be in ControlMode.CM_AUTOMATED. However, 'automation'
            ControlClients that function in ControlMode.CM_PROBLEM will be
            allowed to take over and 'fix' a given problem.
        _control_mode: what ControlMode we are currently running under. A
            ControlClient can only gain control if they request under
            the current control_mode (and no other client is currently
            under control).
        _client_in_control_id: a uuid for the client currently under control.
        _poll_timeout_ms: delay to wait when polling for a request from the
           frontend.
        _req_timeout_ms: delay to wait for a reply from a request we send to
            the backend.
    """

    def __init__(self, server_url: str, router_url: str,
                 ctx: zmq.Context = None,
                 poll_timeout_ms: int = common.POLL_TIMEOUT_MS,
                 request_timeout_ms: int = common.REQUEST_TIMEOUT_MS):
        """Init the class.

        Args:
            server_url: the url of the ControlServer to connect to.
            router_url: the url of the Router, for ControlClients to connect
                to.
            ctx: zmq context.
            poll_timeout_ms: delay to wait when polling for a request from the
                frontend.
            request_timeout_ms: delay to wait for a reply from a request we send
                to the backend.
        """
        if not ctx:
            ctx = zmq.Context.instance()

        self._ctx = ctx
        self._backend_url = server_url
        self._backend = None
        self._init_backend()

        self._frontend = ctx.socket(zmq.ROUTER)
        # Drop old sockets with same uuid
        self._frontend.setsockopt(zmq.ROUTER_HANDOVER, 1)
        self._frontend.bind(router_url)

        self._problems_set = set()

        self._control_mode = control_pb2.ControlMode.CM_AUTOMATED
        self._client_in_control_id = None

        self._poll_timeout_ms = poll_timeout_ms
        self._request_timeout_ms = request_timeout_ms
        self.shutdown_was_requested = False

        common.sleep_on_socket_startup()

    def _init_backend(self):
        """Startup (or restart) the backend socket."""
        if self._backend and not self._backend.closed:
            logger.error("Backend init, but exists and is not closed. "
                         "Do nothing.")
            return
        self._backend = self._ctx.socket(zmq.REQ)
        self._backend.connect(self._backend_url)

    def _close_backend(self):
        """Close the backend socket."""
        self._backend.setsockopt(zmq.LINGER, 0)
        self._backend.close()

    def _handle_control_request(self, client: str,
                                problem: control_pb2.ExperimentProblem,
                                ) -> control_pb2.ControlResponse:
        """Set client in control if possible.

        The client will only be placed under control if:
        - the provided control_mode matches the one this ControlRouter is
            currently under;
        - the ControlRouter is not currently under control.

        Args:
            client: uuid of client.
            problem: ExperimentProblem this client solves (EP_NONE if
                general component).

        Returns:
            - REP_SUCCESS if the above are met.
            - REP_ALREADY_UNDER_CONTROL if already under control.
            - REP_WRONG_CONTROL_MODE if there is a mismatch between
                control_mode of request and the one the ControlClient is
                currently under.
        """
        if self._client_in_control_id and self._client_in_control_id != client:
            logger.debug("%s requested control, but already under control",
                         client)
            return control_pb2.ControlResponse.REP_ALREADY_UNDER_CONTROL

        in_manual_mode = self._control_mode == control_pb2.ControlMode.CM_MANUAL
        generic_request = (problem ==
                           control_pb2.ExperimentProblem.EP_NONE)
        no_problems_and_generic_request = (
            generic_request and len(self._problems_set) == 0)
        solves_problem = problem in self._problems_set

        if (not in_manual_mode and no_problems_and_generic_request or
                solves_problem):
            logger.info("%s gaining control", client)
            self._client_in_control_id = client
            return control_pb2.ControlResponse.REP_SUCCESS

        problems_set_str = {common.get_enum_str(control_pb2.ExperimentProblem,
                                                prblm)
                            for prblm in self._problems_set}
        if in_manual_mode:
            logger.debug("Component %s requested control, but in manual mode",
                         client)
            return control_pb2.ControlResponse.REP_WRONG_CONTROL_MODE
        if generic_request:
            logger.debug("General component %s requested control, but ",
                         "there are logged problems: %s", client,
                         problems_set_str)
        else:  # Problems are logged but the presented is not in our set.
            logger.debug("%s requested control, but resolves problem %s, "
                         "which is not one of our logged problems: %s", client,
                         common.get_enum_str(control_pb2.ExperimentProblem,
                                             problem),
                         problems_set_str)
        return control_pb2.ControlResponse.REP_WRONG_EXP_PROBLEM

    def _handle_control_release(self, client: str) -> control_pb2.ControlResponse:
        """Release client control if applicable.

        Control can only be released by the client who currently has control.

        Args:
            client: uuid of client.

        Returns:
            - REP_SUCCESS if the client was under control; we release.
            - REP_FAILURE if the client releasing was not under
                control to begin with (or no one was under control).
        """
        if self._client_in_control_id and self._client_in_control_id == client:
            logger.info(f"Releasing control from {client}")
            self._client_in_control_id = None
            return control_pb2.ControlResponse.REP_SUCCESS

        logger.debug(f"{client} tried to release control, but in control.")
        return control_pb2.ControlResponse.REP_FAILURE

    def _handle_experiment_problem(self, add_problem: bool,
                                   exp_problem: control_pb2.ExperimentProblem
                                   ) -> control_pb2.ControlResponse:
        """Add or remove ExperimentProblems.

        Args:
            add_problem: if true, add the provided problem. if false, remove it.
            exp_problem: the ExperimentProblem to add/remove.

        Returns:
            ControlMode.SUCCESS if we were able to add it.
        """
        old_mode = copy.deepcopy(self._control_mode)
        if add_problem:
            logger.warning("Adding problem %s",
                           common.get_enum_str(control_pb2.ExperimentProblem,
                                               exp_problem))
            self._problems_set.add(exp_problem)
        else:
            logger.warning("Removing problem %s",
                           common.get_enum_str(control_pb2.ExperimentProblem,
                                               exp_problem))
            self._problems_set.remove(exp_problem)

        if self._problems_set:
            self._control_mode = control_pb2.ControlMode.CM_PROBLEM
            if old_mode != control_pb2.ControlMode.CM_PROBLEM:
                logger.warning("Entering problem mode")
                self._client_in_control_id = None
        elif old_mode == control_pb2.ControlMode.CM_PROBLEM:
            logger.warning("Exiting problem mode, switching to automated.")
            self._control_mode = control_pb2.ControlMode.CM_AUTOMATED
            self._client_in_control_id = None

        # Return success always for now...
        return control_pb2.ControlResponse.REP_SUCCESS

    def _handle_send_req(self, req: control_pb2.ControlRequest,
                         proto: Message) -> (control_pb2.ControlResponse,
                                             Message | int | None):
        """Try to send a request to the ControlServer.

        For a request received from the client under control, try to forward
        it to the ControlServer.

        Note: we don't do extra handling for no response; we expect that
        to be handled by the client.

        Args:
            req: the control request to be sent.
            proto: the associated protobuf message, if applicable.

        Returns:
            (ControlResponse, obj) received from the ControlServer. Note that
            in all but a few cases, obj will be None as there is no associated
            obj.
        """
        logger.debug("Handling send request: %s, %s",
                     common.get_enum_str(control_pb2.ControlRequest, req), proto)
        msg = cmd.serialize_request(req, proto)  # No need for empty envelope
        self._backend.send_multipart(msg)

        if (self._backend.poll(self._request_timeout_ms) & zmq.POLLIN) != 0:
            return cmd.parse_response(req, self._backend.recv_multipart())

        logger.error("Backend did not respond in time, likely timeout issue."
                     "Restarting socket. ")
        self._close_backend()
        self._init_backend()

        return (control_pb2.ControlResponse.REP_NO_RESPONSE, None)

    def _handle_set_control_mode(self, control_mode: control_pb2.ControlMode
                                 ) -> control_pb2.ControlResponse:
        """Change the control mode.

        Args:
            control_mode: ControlMode to change to.

        Returns:
            ControlResponse indicating success/failure.
        """
        logger.info(f"Control mode changed to {control_mode}")
        self._control_mode = control_mode
        self._client_in_control_id = None
        return control_pb2.ControlResponse.REP_SUCCESS

    def _handle_end_experiment(self) -> control_pb2.ControlResponse:
        """End the experiment.

        This call will update internal logic indicating a shutdown was
        requested. It may be used externally to shutdown/pass the request
        on, etc.
        """
        logger.info("End of experiment requested.")
        self.shutdown_was_requested = True
        return control_pb2.ControlResponse.REP_SUCCESS

    def _on_request(self, client: str, req: control_pb2.ControlRequest,
                    obj: Message | int) -> (control_pb2.ControlResponse,
                                            Message | int | None):
        """Handle a request received by a ControlClient.

        Args:
            client: ControlClient uuid.
            req: control request received.
            obj: protobuf message or int enum linked to request, if applicable.

        Returns:
            (ControlResponse, obj) to the request. Note that in all but a few
            cases, obj will be None as there is no returned obj to the request.
        """
        if req == control_pb2.ControlRequest.REQ_REQUEST_CTRL:
            return (self._handle_control_request(client, obj), None)
        if req == control_pb2.ControlRequest.REQ_RELEASE_CTRL:
            return (self._handle_control_release(client), None)
        if req in [control_pb2.ControlRequest.REQ_ADD_EXP_PRBLM,
                   control_pb2.ControlRequest.REQ_RMV_EXP_PRBLM]:
            return (self._handle_experiment_problem(
                req == control_pb2.ControlRequest.REQ_ADD_EXP_PRBLM, obj),
                    None)
        if req == control_pb2.ControlRequest.REQ_SET_CONTROL_MODE:
            return (self._handle_set_control_mode(obj), None)
        if req == control_pb2.ControlRequest.REQ_END_EXPERIMENT:
            return (self._handle_end_experiment(), None)
        if (self._client_in_control_id
                and client == self._client_in_control_id):
            return self._handle_send_req(req, obj)
        return (control_pb2.ControlResponse.REP_NOT_IN_CONTROL, None)

    def poll_and_handle(self):
        """Poll for ControlClient requests and handle."""
        msg = None
        if self._poll_timeout_ms:
            if self._frontend.poll(self._poll_timeout_ms, zmq.POLLIN):
                msg = self._frontend.recv_multipart(zmq.NOBLOCK)
        else:
            msg = self._frontend.recv_multipart()

        if msg:
            client = msg[0]
            client_id = self._parse_client_id(client)
            req, obj = cmd.parse_request(msg[2:])  # client, __, ...

            logger.debug("Message received from client %s: %s, %s", client_id,
                         common.get_enum_str(control_pb2.ControlRequest, req),
                         obj)

            rep, obj = self._on_request(client_id, req, obj)

            logger.debug("Sending reply to %s: %s, %s", client_id,
                         common.get_enum_str(control_pb2.ControlResponse, rep),
                         obj)
            self._frontend.send_multipart([client, b""] +  # Concat lists
                                          cmd.serialize_response(rep, obj))

    def get_control_state(self):
        """Create and return a ControState instance from current state."""
        state = control_pb2.ControlState()
        state.control_mode = self._control_mode
        if self._client_in_control_id:
            state.client_in_control_id = self._client_in_control_id
        state.problems_set.extend(self._problems_set)
        return state

    @staticmethod
    def _parse_client_id(msg: list[bytes]) -> str:
        """Parse the received client id to a string.

        The received client id will either be:
        - an int, if no zmq.IDENTITY was explicited for the socket;
        - a str, if a zmq.IDENTITY was explicited for the socket.

        Args:
            msg: client id received as a bytes array.

        Returns:
            string associated with the cliend id.
        """
        try:
            return msg.decode()  # zmq.IDENTITY used
        except UnicodeDecodeError:
            return str(int.from_bytes(msg, 'big'))
