"""Holds Nanonis controller parameters (and other extra logic)."""

import logging
import enum
from dataclasses import dataclass, replace, astuple, fields
from typing import Any

from ... import params
from .....utils.parser import _evaluate_value_str
from .client import NanonisClient
from .message import base


logger = logging.getLogger(__name__)


@dataclass
class NanonisParameterInfo(params.ParameterInfo):
    """Expanding ParameterInfo to be used for Nanonis params.

    Here, we are adding an attribute and modifying one for our needs.

    uuid (modified):
    ----

    this now refers to the 'prefix' for the various NanonisMessages
    associated to this call. Each API call is linked to:
    - A VARIABLEStruct NanonisMessage, which is a dataclass containing
    the structure of the buffer we will send/receive.
    - A VARIABLESet NanonisMessage, which contains the setter command
    name.
    - A VARIABLEGet NanonisMessage, which contains the getter command
    name.
    - VARIABLESetReq / VARIABLESetRep and VARIABLEGetReq / VARIABLEGetRep
    messages, which inherit from the appropriate about messages. For
    example, to set the voltage bias, BiasSetReq inherits from
    BiasStruct, while BiasSetRep inehrits from EmptyResponse.

    Here, VARIABLE is the 'prefix'. So, we indicate which NanonisMessages
    to use for a given call by setting uuid to VARIABLE. Note that these
    will be imported in the same way as the getter/setter, so you should
    include the full path to it.

    index (added):
    -----

    This is an added parameter. It is to hold the index of the VARIABLEStruct
    associated to this particular parameter. The reason is that Nanonis
    bundles various parameters into composite ones, so a given generic
    parameter may only be accessible by querying the composite parameter
    and extracting the individual parameter of interest (via its index).

    If the generic parameter maps to an individual parameter (i.e. not
    a composite), you can likely set index to 0. This is best determined
    by reviewing the associated NanonisMessage.
    """

    index: int  # Indicates VARIABLEStruct index for this parameter.


def create_param_info(param_dict: dict) -> NanonisParameterInfo:
    """Like params.create_parameter_info, but for NanonisParameterInfo."""
    vals = []
    for key in NanonisParameterInfo.__annotations__.keys():
        vals.append(param_dict[key] if key in param_dict else None)
    return NanonisParameterInfo(*vals)


class NanonisParameterHandler(params.ParameterHandler):
    """Implements Nanonis-specific logic for parameter handling.

    Attributes:
        _client: TCP client used to communicate with Nanonis.
        _uuid_to_reqrep_get_map: holds a NanonisReqRep instance
            tied to a get call for a given specific uuid.
        _uuid_to_reqrep_set_map: holds a NanonisReqRep instance
            tied to a set call for a given specific uuid.
        _uuid_to_struct_index_map: holds the NanonisMessage's attribute index
            for a given parameter. (Remember, many parameters are stored in
            composite structures, so they will be one of many and thus have
            an index.)
    """

    def __init__(self, client: NanonisClient,
                 **kwargs):
        """Override create_parameter_info for our special one.

        Args:
            client: TCP client used to communicate with Nanonis.
        """
        self._client = client
        self._uuid_to_reqrep_get_map = {}
        self._uuid_to_reqrep_set_map = {}
        self._uuid_to_struct_index_map = {}

        kwargs['param_info_init'] = create_param_info
        self.__init__(**kwargs)

    def _load_config_build_params(self, params_config_path: str):
        """Override, to populate Message mapping for all ParameterInfos.

        For Nanonis ParameterInfos in our TOML, we feed the module + message
        prefix for instantiation. Rather than evaluating every time, we
        populate self._prefix_to_messages.
        """
        super()._load_config_build_params(params_config_path)

        # Populate specific_uuid-to-reqrep mappings
        for key, val in self.param_infos.items():
            struct = _evaluate_value_str(val.uuid + base.STRUCT)

            # Store get information
            req = _evaluate_value_str(val.uuid + base.GET_REQ)
            rep = _evaluate_value_str(val.uuid + base.GET_REP)
            reqrep = base.NanonisReqRep(req, rep, struct)
            self._uuid_to_reqrep_get_map[val.uuid] = reqrep

            # Store set information
            req = _evaluate_value_str(val.uuid + base.SET_REQ)
            rep = _evaluate_value_str(val.uuid + base.SET_REP)
            reqrep = base.NanonisReqRep(req, rep, struct)
            self._uuid_to_reqrep_set_map[val.uuid] = reqrep

            # Store index information
            self._uuid_to_struct_index_map[val.uuid] = val.index

        self._load_status_logic()

    def _load_status_logic(self):
        """Load status Req/Rep logic, which is not in the TOMLs.

        These particular message types are get-only.
        """
        self.param_infos.update(_create_status_param_info_entries())
        self._uuid_to_reqrep_get_map.update(
            _create_status_reqrep_map_entries())
        self._uuid_to_struct_index_map.update(
            _create_status_struct_index_entries())

    # --- Helpers to try/catch KeyErrors --- #
    def _get_req_rep_get(self, spm_uuid: str) -> base.NanonisReqRep:
        """Getter of GET ReqRep with KeyError handling."""
        try:
            req_rep = self._uuid_to_reqrep_get_map[spm_uuid]
        except KeyError:
            msg = f'Could not find GET NanonisReqRep for {spm_uuid}.'
            logger.error(msg)
            raise params.ParameterConfigurationError(msg)
        return req_rep

    def _get_req_rep_set(self, spm_uuid: str) -> base.NanonisReqRep:
        """Getter of SET ReqRep with KeyError handling."""
        try:
            req_rep = self._uuid_to_reqrep_set_map[spm_uuid]
        except KeyError:
            msg = f'Could not find SET NanonisReqRep for {spm_uuid}.'
            logger.error(msg)
            raise params.ParameterConfigurationError(msg)
        return req_rep

    def _get_struct_idx(self, spm_uuid: str) -> int:
        """Getter of NanonisMessage attribute index with KeyError handling."""
        try:
            idx = self._uuid_to_struct_index_map[spm_uuid]
        except KeyError:
            msg = f'Could not find Nanonis struct index for {spm_uuid}.'
            logger.error(msg)
            raise params.ParameterConfigurationError(msg)
        return idx
    # --- End KeyError catching helpers --- #

    def _get_param_spm_struct(self, spm_uuid: str
                              ) -> base.NanonisResponse | None:
        """Like get_param_spm(), but we return the NanonisResponse."""
        req_rep = self._get_req_rep_get(spm_uuid)

        requested_response = req_rep.req.request_response()
        req_buffer = base.to_bytes(req_rep.req)
        rep_buffer = self._client.send_request(req_buffer, requested_response)

        if requested_response:
            get_rep = base.from_bytes(rep_buffer, req_rep.rep,
                                      requested_response)
            return get_rep
        return None

    def get_param_spm(self, spm_uuid: str) -> Any:
        """Implement.

        In this implementation, spm_uuid is in fact a str containing
        the module + class prefix for importing necessary Python objects
        in order to send the request. Look for VARIABLE in the class
        pydoc above.

        Note, however, that we *also* need the index of the struct we are
        getting
        """
        get_rep = self._get_param_spm_struct(spm_uuid)
        if get_rep:
            val_idx = self._uuid_to_struct_index_map[spm_uuid]
            val = astuple(get_rep)[val_idx]
            return val
        return None

    def _obtain_set_struct(self, spm_uuid: str) -> base.NanonisMessage:
        """Obtain structure we will be using to set.

        Many of the parameters we wish to set are part of a composite structure
        which causes us to need to 'get' the current state of the structure
        first. This is notably  not the case for *all* parameters. This method
        will return the base structure, either (a) via getting the composite
        struct or (b) grabbing from our reqrep map.
        """
        req_rep = self._get_req_rep_set(spm_uuid)

        if len(astuple(req_rep.req)) > 1:
            return self._get_param_spm_struct(spm_uuid)
        return req_rep.req

    def _prepare_set_struct(self, spm_uuid: str, spm_val: Any
                            ) -> base.NanonisMessage:
        """Populate a structure for setting.

        Here, we obtain the base structure associated with our set call and
        modify the appropriate attribute (linked to our parameter of interest).
        The returned structure is ready to be sent out to our setter method.
        """
        idx = self._get_struct_idx(spm_uuid)
        get_rep = self._obtain_set_struct(spm_uuid)

        tuple_data = astuple(get_rep)
        tuple_data[idx] = spm_val

        # Fill set request with struct data (should match our get reply
        # structure).
        set_req = self._uuid_to_reqrep_set_map.req
        set_req = replace(set_req, dict(zip(fields(set_req), tuple_data)))
        return set_req

    def set_param_spm(self, spm_uuid: str, spm_val: Any):
        """Implement.

        Because many of the parameters we set are settable via composite
        structures, we largely have to call a 'get' method before setting,
        obtaining the current values. This is done in _obtain_set_struct().

        For composite sets from within afspm (e.g., ScanParameters2d), I
        suggest manually using these internal methods. Otherwise, the
        approach taken here will call N gets and sets for the N attributes of
        the afspm-composite struct.

        # TODO: Do you need a special check for gain? You may need to ensure
        # the P and I are properly linked.
        # In fact, it may be smarter to deal with t or 1/t, because otherwise
        # P and I are very clearly linked? Consider changing I-gain
        # in params TOML accordingly...
        """
        set_req = self._prepare_set_struct(spm_uuid, spm_val)
        req_buffer = base.to_bytes(set_req)

        requested_response = set_req.request_response()
        rep_buffer = self._client.send_request(req_buffer, requested_response)
        if requested_response:
            # Receive response (in case we catch an error), but do  not
            # parse it (because there should be no struct sent back).
            set_rep = self._get_req_rep_set(spm_uuid).rep
            base.from_bytes(rep_buffer, set_rep, requested_response)


# ---- Special Conversions ----- #
# Special conversions due to differences between Nanonis and our generic model.


class NanonisParam(params.MicroscopeParameter):
    """Nanonis-specific parameters, used as 'generic' names in config.

    We use the 'name' of these parameters as their generic uuid when
    querying them from the params config. So, for example, for CENTER_X,
    we expect:
        [center_x]
        uuid = 'something'
        [...]
    In the config file.
    """

    CENTER_X = 'center-x'
    CENTER_Y = 'center-y'

    # Status params (getters only)
    SCAN_STATUS = 'scan-status'
    BIAS_SPEC_STATUS = 'bias-spec-status'
    Z_SPEC_STATUS = 'z-spec-status'


# ----- Top-Left Position Methods ----- #
def center_to_top_left(pos: float, size: float):
    """Go from center -> TL."""
    return pos + 0.5*size


def top_left_to_center(pos: float, size: float):
    """Go from center -> TL."""
    return pos - 0.5*size


def set_scan_x(handler: params.ParameterHandler,
               val: Any, unit: str):
    """Set top-left x-position of scan.

    Nanonis stores the center position, so we need to subtract half of
    (width/height) to what we receive.
    """
    # Get scan_size_x
    size = handler.get_param(params.MicroscopeParameter.SCAN_SIZE_X)
    pos = top_left_to_center(val, size)
    handler.set_param(NanonisParam.CENTER_X, pos, unit)


def set_scan_y(handler: params.ParameterHandler,
               val: Any, unit: str):
    """Set top-left y-position of scan.

    Nanonis stores the center position, so we need to subtract half of
    (width/height) to what we receive.
    """
    size = handler.get_param(params.MicroscopeParameter.SCAN_SIZE_Y)
    pos = top_left_to_center(val, size)
    handler.set_param(NanonisParam.CENTER_Y, pos, unit)


def set_scan_speed(handler: params.ParameterHandler,
                   val: Any, unit: str):
    """Set scan speed.

    This is a special method, since Nanonis allows you to set the forward
    and backward scan speeds independently. Because our framework only
    supports a generic 'scan-speed', we set the forward one and maintain
    the pre-existing ratio between forward and backward.
    """
    generic_uuid = params.MicroscopeParameter.SCAN_SPEED
    param_info = handler._get_param_info(generic_uuid)

    if param_info.uuid is None:
        msg = f'Parameter {generic_uuid} does not have SPM uuid.'
        logger.error(msg)
        raise params.ParameterNotSupportedError(msg)

    # TODO: Set this attr *AND* the ratio between forward and backward.
    # Also, make sure you set const to 0 for this struct.


# ----- Hard-coded status logic ----- #
# The parameters here don't fit into the standard set/get paradigm,
# but only have a get (they are statuses).
# Since we only use these to check the current ScopeState, we are just
# hard-coding the logic here.

# Special parameters for get only (ScanAction is needed for actions.py)
BASE_UUID = 'afspm.components.microscope.translators.nanonis.message.'

SCAN_STATUS_UUID = 'afspm.components.microscope.translators.nanonis.message.scan.ScanStatus'
BIAS_SPEC_STATUS_UUID = 'afspm.components.microscope.translators.nanonis.message.spectroscopy.BiasSpectraStatus'
Z_SPEC_STATUS_UUID = 'afspm.components.microscope.translators.nanonis.message.spectroscopy.ZSpectraStatus'

STATUS_GENERIC_IDS = [NanonisParam.SCAN_STATUS, NanonisParam.BIAS_SPEC_STATUS,
                      NanonisParam.Z_SPEC_STATUS]
STATUS_UUIDS = [BASE_UUID + 'scan.ScanStatus',
                BASE_UUID + 'spectroscopy.BiasSpectraStatus',
                BASE_UUID + 'spectroscopy.ZSpectraStatus']


def _create_status_param_info_entries() -> dict:
    """Create status param info entries, outputting a dict of these.

    We do this rather than polute the params TOML with them. It is also
    worth doing explicitly, as these ones do not have setters!

    Returns:
        param_info_map-like dict, which can be joined with the one in
            NanonisParameterHandler.
    """
    param_info_map = {}
    for generic_id, uuid in zip(STATUS_GENERIC_IDS, STATUS_UUIDS):
        info = params.ParameterInfo(uuid, type=1)  # int for all statuses
        param_info_map[generic_id] = info
    return param_info_map


def _create_status_reqrep_map_entries() -> dict:
    """Create status NanonisReqRep entries, outputting a dict of these.

    We do this rather than polute the params TOML with them. It is also
    worth doing explicitly, as these ones do not have setters!

    Returns:
        uuid_to_reqrep_get_map-like dict, which can be joined with the
            one in NanonisParameterHandler.
    """
    reqrep_map = {}
    for uuid in STATUS_UUIDS:
        struct = _evaluate_value_str(uuid + base.STRUCT)

        # Store get information
        req = _evaluate_value_str(uuid + base.GET_REQ)
        rep = _evaluate_value_str(uuid + base.GET_REP)
        reqrep = base.NanonisReqRep(req, rep, struct)
        reqrep_map[uuid] = reqrep
    return reqrep_map


def _create_status_struct_index_entries() -> dict:
    """Create index entries for our status parameters.

    Returns:
        uuid_to_struct_index_map-like dict, which can be joined with the one
            in NanonisParameterHandler.
    """
    index_map = {}
    for uuid in STATUS_UUIDS:
        index_map[uuid] = 0
    return index_map
