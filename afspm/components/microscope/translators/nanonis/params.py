"""Holds Nanonis controller parameters (and other extra logic)."""

import logging
from dataclasses import dataclass, replace, astuple
from typing import Any

from ... import params
from .....utils.parser import _evaluate_value_str
from . import client as clnt
from .message import base, scan


logger = logging.getLogger(__name__)


@dataclass
class NanonisParameterInfo(params.ParameterInfo):
    """Expanding ParameterInfo to be used for Nanonis params.

    Here, we add two new attributes:
    - class_name: a str indicating the class prefix we will be importing
    (tied to the req/rep).
    - index: int indicating the struct index of the parameter of interest.

    class_name:
    ----

    This refers to the 'prefix' for the various NanonisMessages
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

    index:
    -----

    This is an added parameter. It is to hold the index of the VARIABLEStruct
    associated to this particular parameter. The reason is that Nanonis
    bundles various parameters into composite ones, so a given generic
    parameter may only be accessible by querying the composite parameter
    and extracting the individual parameter of interest (via its index).

    If the generic parameter maps to an individual parameter (i.e. not
    a composite), you can likely set index to 0. This is best determined
    by reviewing the associated NanonisMessage.

    uuid:
    -----

    Rather than providing the uuid, this class creates the uuid in its
    __post_init__() method.

    We have modified the method overrides to clarify this.
    """

    uuid: tuple[str, int]
    class_name: str
    index: int  # Indicates VARIABLEStruct index for this parameter.

    def __post_init__(self):
        """Configure uuid."""
        self.configure_uuid()

    def configure_uuid(self):
        """Set up the uuid based on other attributes."""
        uuid = (self.class_name, self.index)
        if None not in uuid:
            self.uuid = uuid


def validate_parameter(param_info: params.ParameterInfo,
                       param_methods: params.ParameterMethods,
                       gid: str) -> (params.ParameterInfo | None,
                                     params.ParameterMethods | None):
    """Override for NanonisParameterInfo."""
    param_methods_met = None not in [param_methods.getter,
                                     param_methods.setter]
    param_info_met = None not in [param_info.type, param_info.class_name,
                                  param_info.index]

    if param_methods_met or param_info_met:
        if params._all_none(param_methods):
            param_methods = None
        if params._all_none(param_info):
            param_info = None
    return (param_info, param_methods)


class NanonisParameterHandler(params.ParameterHandler):
    """Implements Nanonis-specific logic for parameter handling.

    Attributes:
        _client: TCP client used to communicate with Nanonis.
        _class_name_to_reqrep_get_map: holds a NanonisReqRep instance
            tied to a get call for a given specific uuid.
        _class_name_to_reqrep_set_map: holds a NanonisReqRep instance
            tied to a set call for a given specific uuid.
    """

    def __init__(self, client: clnt.NanonisClient,
                 **kwargs):
        """Override create_parameter_info for our special one.

        Args:
            client: TCP client used to communicate with Nanonis.
        """
        self._client = client
        self._class_name_to_reqrep_get_map = {}
        self._class_name_to_reqrep_set_map = {}

        kwargs['param_info_class'] = NanonisParameterInfo
        kwargs['validate_parameter'] = validate_parameter
        super().__init__(**kwargs)

    def _load_config_build_params(self, params_config_path: str):
        """Override, to populate Message mapping for all ParameterInfos.

        For Nanonis ParameterInfos in our TOML, we feed the module + message
        prefix for instantiation. Rather than evaluating every time, we
        populate self._prefix_to_messages.
        """
        super()._load_config_build_params(params_config_path)

        # Populate specific_uuid-to-reqrep mappings
        for key, val in self.param_infos.items():
            # Store get information
            req = _evaluate_value_str(val.class_name + base.GET_REQ)()
            rep = _evaluate_value_str(val.class_name + base.GET_REP)()
            reqrep = base.NanonisReqRep(req, rep)
            self._class_name_to_reqrep_get_map[val.class_name] = reqrep

            # Store set information
            req = _evaluate_value_str(val.class_name + base.SET_REQ)()
            rep = _evaluate_value_str(val.class_name + base.SET_REP)()
            reqrep = base.NanonisReqRep(req, rep)
            self._class_name_to_reqrep_set_map[val.class_name] = reqrep

        # Set up hard-coded parameters
        self._load_status_logic()
        self._load_spec_setting_logic()

    def _load_status_logic(self):
        """Load status Req/Rep logic, which is not in the TOMLs.

        These particular message types are get-only.
        """
        self.param_infos.update(_create_status_param_info_entries())
        self._class_name_to_reqrep_get_map.update(
            _create_status_reqrep_map_entries())

    def _load_spec_setting_logic(self):
        self.param_infos.update(_create_spec_setting_param_info_entries())
        self._class_name_to_reqrep_set_map.update(
            _create_spec_setting_reqrep_map_entries())

    # --- Helpers to try/catch KeyErrors --- #
    def _get_getter_req_rep(self, class_name: str) -> base.NanonisReqRep:
        """Getter of GET ReqRep with KeyError handling."""
        try:
            req_rep = self._class_name_to_reqrep_get_map[class_name]
        except KeyError:
            msg = f'Could not find GET NanonisReqRep for {class_name}.'
            raise params.ParameterConfigurationError(msg)
        return req_rep

    def _get_setter_req_rep(self, class_name: str) -> base.NanonisReqRep:
        """Getter of SET ReqRep with KeyError handling."""
        try:
            req_rep = self._class_name_to_reqrep_set_map[class_name]
        except KeyError:
            msg = f'Could not find SET NanonisReqRep for {class_name}.'
            raise params.ParameterConfigurationError(msg)
        return req_rep
    # --- End KeyError catching helpers --- #

    def _get_param_spm_rep(self, class_name: str
                           ) -> base.NanonisResponse | None:
        """Like get_param_spm(), but we return the NanonisResponse."""
        req_rep = self._get_getter_req_rep(class_name)
        req = req_rep.req
        rep = (req_rep.rep if req.request_response() else None)
        return self.send_request(req, rep)

    def get_param_spm(self, spm_uuid: tuple[str, int]) -> Any:
        """Implement.

        In this implementation, spm_uuid is in fact a str containing
        the module + class prefix for importing necessary Python objects
        in order to send the request. Look for VARIABLE in the class
        pydoc above.

        Note, however, that we *also* need the index of the struct we are
        getting
        """
        class_name = spm_uuid[0]
        index = spm_uuid[1]
        get_rep = self._get_param_spm_rep(class_name)

        if get_rep:
            val = astuple(get_rep)[index]
            return val
        return None

    def _obtain_base_set_req(self, class_name: str) -> base.NanonisRequest:
        """Obtain base request we will be using to set.

        Many of the parameters we wish to set are part of a composite structure
        which causes us to need to 'get' the current state of the structure
        first. This is notably  not the case for *all* parameters. This method
        will return the base request, either (a) via getting the composite
        struct or (b) grabbing from our reqrep map.

        Note also that some parameter setters do not have associated getters.
        We catch such an exception here and log it. We do not do the same
        in the main get()/set() calls because we should not be explicitly
        getting or setting something that (we should know) does not exist.
        """
        set_req = self._get_setter_req_rep(class_name).req

        # If dealing with composite parameter, call get() to obtain initial
        # vals (so we don't overwrite/change the other parameters when
        # setting).
        if len(astuple(set_req)) > 1:
            try:
                get_rep = self._get_param_spm_rep(class_name)
                return copy_data(get_rep, set_req)
            except params.ParameterConfigurationError:
                logger.debug(f'Not getting initial values for {class_name},'
                             ' due to GET() not existing.')
                pass
        return set_req

    def _prepare_set_req(self, class_name: str, index: int, spm_val: Any
                         ) -> base.NanonisMessage:
        """Obtain and populate a NanonisRequest for setting.

        Here, we obtain the base structure associated with our set call and
        modify the appropriate attribute (linked to our parameter of interest).
        The returned structure is ready to be sent out to our setter method.
        """
        set_req = self._obtain_base_set_req(class_name)

        list_data = list(astuple(set_req))
        list_data[index] = spm_val
        return copy_data_from_tuple(tuple(list_data), set_req)

    def set_param_spm(self, spm_uuid: tuple[str, int], spm_val: Any):
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
        class_name = spm_uuid[0]
        index = spm_uuid[1]

        req = self._prepare_set_req(class_name, index, spm_val)
        rep = (self._get_setter_req_rep(class_name).rep
               if req.request_response() else None)
        self.send_request(req, rep)

    def send_request(self, req: base.NanonisRequest,
                     rep: base.NanonisResponse
                     ) -> base.NanonisResponse | None:
        """Given a filled out req, send out."""
        return send_request(self._client, req, rep)

    def populate_req(self, req: base.NanonisRequest,
                     gids: list[params.MicroscopeParameter],
                     vals: list[Any], units: list[str]) -> base.NanonisRequest:
        """Fill a request with the provided values.

        This will populate the vals associated with gids into the provided
        request. We use _correct_val_for_sending() to ensure each value is
        properly set.

        Args:
            req: NanonisRequest we are populating.
            gids: generic ids for each value in vals.
            vals: vals we are setting.
            units: units of each value in vals.
        """
        param_infos = [self._get_param_info(gid) for gid in gids]
        indices = [self._get_param_info(gid).index for gid in gids]
        new_vals = [params._correct_val_for_sending(val, param_info, unit, gid)
                    for val, gid, unit, param_info in zip(vals, gids, units,
                                                          param_infos)]

        list_data = list(astuple(req))
        for index, val in zip(indices, new_vals):
            list_data[index] = val
        return copy_data_from_tuple(tuple(list_data), req)


def copy_data(copy_from: base.NanonisMessage,
              copy_to: base.NanonisMessage
              ) -> base.NanonisMessage:
    """Copy the data from one message to another.

    This implicitly assumes copy_to and copy_from have the same attributes,
    which would be the case if they correspond to linked messages (e.g.
    a ScanBufferSetReq and a ScanBufferGetRep).

    Args:
        copy_from: NanonisMessage we will copy data from.
        copy_to: NanonisMessage we will copy data to.

    Returns:
        Instance of copy_to, with data copied from copy_from.
    """
    return copy_data_from_tuple(astuple(copy_from), copy_to)


def copy_data_from_tuple(tuple_data: (Any,),
                         copy_to: base.NanonisMessage
                         ) -> base.NanonisMessage:
    """Equivalen to copy_data(), but copy_from is tuple."""
    return replace(copy_to, **copy_to.create_data_dict(tuple_data))


def send_request(client: clnt.NanonisClient, req: base.NanonisRequest,
                 rep: base.NanonisResponse | None
                 ) -> base.NanonisResponse | None:
    """Wrap client.py method, with Exception swapping."""
    try:
        return clnt.send_request(client, req, rep)
    except clnt.NanonisCommunicationError as e:
        raise params.ParameterError(str(e))


# ---- Special Conversions ----- #
# Special conversions due to differences between Nanonis and our generic model.


class NanonisParam(params.MicroscopeParameterBase):
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

    # The system path is same as save path
    FILE_PATH = 'file-path'

    # Scan startup settings
    SCAN_CONTINUOUS_SCAN = 'scan-continuous-scan'
    SCAN_AUTO_SAVE = 'scan-auto-save'

    # Spectra startup settings (setters only)
    BIAS_SPEC_AUTO_SAVE = 'bias-spec-auto-save'
    BIAS_SHOW_SAVE_DIALOG = 'bias-spec-save-dialog'
    Z_SPEC_AUTO_SAVE = 'z-spec-auto-save'
    Z_SHOW_SAVE_DIALOG = 'bias-spec-save-dialog'


# ----- Top-Left Position Methods ----- #
def center_to_top_left(pos: float, size: float):
    """Go from center -> TL."""
    return pos - 0.5*size


def top_left_to_center(pos: float, size: float):
    """Go from center -> TL."""
    return pos + 0.5*size


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


def get_scan_x(handler: params.ParameterHandler) -> Any:
    """Get top-left x-position of scan.

    Nanonis stores the center position, so we need to add half of
    (width/height) to what we receive.
    """
    generic_ids = [NanonisParam.CENTER_X,
                   params.MicroscopeParameter.SCAN_SIZE_X]
    vals = handler.get_param_list(generic_ids)
    return center_to_top_left(vals[0], vals[1])


def get_scan_y(handler: params.ParameterHandler) -> Any:
    """Get top-left y-position of scan.

    Nanonis stores the center position, so we need to add half of
    (width/height) to what we receive.
    """
    generic_ids = [NanonisParam.CENTER_Y,
                   params.MicroscopeParameter.SCAN_SIZE_Y]
    vals = handler.get_param_list(generic_ids)
    return center_to_top_left(vals[0], vals[1])


def set_scan_speed(handler: params.ParameterHandler,
                   val: Any, unit: str):
    """Set scan speed.

    This is a special method, since Nanonis allows you to set the forward
    and backward scan speeds independently. Because our framework only
    supports a generic 'scan-speed', we set the forward one and maintain
    the pre-existing ratio between forward and backward.
    """
    gid = params.MicroscopeParameter.SCAN_SPEED
    param_info = handler._get_param_info(gid)
    class_name = param_info.class_name
    speed_req = handler._obtain_base_set_req(class_name)

    # Range / type handling
    val = params._correct_val_for_sending(val, param_info, unit,
                                          gid)

    # Set structure
    speed_req.fwd_speed = val
    speed_req.bwd_speed = val
    # TODO: Test is const should be LINEAR_SPEED or NO_CHANGE.
    speed_req.keep_parameter_constant = scan.ScanSpeedConstant.LINEAR_SPEED
    speed_req.speed_ratio = 1.0  # fwd/bwd speed should be same

    # Send
    speed_rep = handler._get_setter_req_rep(class_name).rep
    handler.send_request(speed_req, speed_rep)


# ----- Hard-coded status logic ----- #
# The parameters here don't fit into the standard set/get paradigm,
# but only have a get (they are statuses).
# Since we only use these to check the current ScopeState, we are just
# hard-coding the logic here.

# Special parameters for get only (ScanAction is needed for actions.py)
BASE_CLASS = 'afspm.components.microscope.translators.nanonis.message.'
STATUS_GENERIC_IDS = [NanonisParam.SCAN_STATUS, NanonisParam.BIAS_SPEC_STATUS,
                      NanonisParam.Z_SPEC_STATUS, NanonisParam.FILE_PATH]
STATUS_GENERIC_INDICES = [0, 0, 0, 1]
STATUS_CLASSES = [BASE_CLASS + 'scan.ScanStatus',
                  BASE_CLASS + 'spectroscopy.BiasSpectraStatus',
                  BASE_CLASS + 'spectroscopy.ZSpectraStatus',
                  BASE_CLASS + 'util.SessionPath']


def _create_status_param_info_entries() -> dict:
    """Create status param info entries, outputting a dict of these.

    We do this rather than polute the params TOML with them. It is also
    worth doing explicitly, as these ones do not have setters!

    Returns:
        param_info_map-like dict, which can be joined with the one in
            NanonisParameterHandler.
    """
    param_info_map = {}
    for generic_id, class_name, index in zip(STATUS_GENERIC_IDS,
                                             STATUS_CLASSES,
                                             STATUS_GENERIC_INDICES):
        info = NanonisParameterInfo(uuid=None, unit=None, range=None,
                                    class_name=class_name, index=index,
                                    type=1)  # int for all statuses
        param_info_map[generic_id] = info
    return param_info_map


def _create_status_reqrep_map_entries() -> dict:
    """Create status NanonisReqRep entries, outputting a dict of these.

    We do this rather than polute the params TOML with them. It is also
    worth doing explicitly, as these ones do not have setters!

    Returns:
        class_name_to_reqrep_get_map-like dict, which can be joined with the
            one in NanonisParameterHandler.
    """
    reqrep_map = {}
    for class_name in STATUS_CLASSES:
        # Store get information
        req = _evaluate_value_str(class_name + base.GET_REQ)()
        rep = _evaluate_value_str(class_name + base.GET_REP)()
        reqrep = base.NanonisReqRep(req, rep)
        reqrep_map[class_name] = reqrep
    return reqrep_map


# ----- Hard-coded spec autosave properties ----- %
# The set and get structures for spectroscopy props are quite dissimilar,
# and in fact the getter does not return the info we want (autosave and
# save dialog). So, we only have structs defined for the setters and
# manually add them via methods here.

SPEC_SETTING_GENERIC_IDS = [NanonisParam.BIAS_SPEC_AUTO_SAVE,
                            NanonisParam.BIAS_SHOW_SAVE_DIALOG,
                            NanonisParam.Z_SPEC_AUTO_SAVE,
                            NanonisParam.Z_SHOW_SAVE_DIALOG]
SPEC_SETTING_CLASSES = [BASE_CLASS + 'spectroscopy.BiasSpectraProps',
                        BASE_CLASS + 'spectroscopy.BiasSpectraProps',
                        BASE_CLASS + 'spectroscopy.ZSpectraProps',
                        BASE_CLASS + 'spectroscopy.ZSpectraProps']
SPEC_SETTING_INDICES = [5, 6, 3, 4]


def _create_spec_setting_param_info_entries() -> dict:
    """Equivalent to _create_status_param_info_entries() for spec setting."""
    param_info_map = {}
    for generic_id, class_name in zip(SPEC_SETTING_GENERIC_IDS,
                                      SPEC_SETTING_CLASSES):
        info = NanonisParameterInfo(uuid=None, unit=None, range=None,
                                    class_name=class_name, index=0,
                                    type=1)  # int for all statuses
        param_info_map[generic_id] = info
    return param_info_map


def _create_spec_setting_reqrep_map_entries() -> dict:
    """Equivalent to _create_status_reqrep_map_entries() for spec setting.

    In this case, only setters are added.
    """
    reqrep_map = {}
    for class_name in SPEC_SETTING_CLASSES:
        # Store get information
        req = _evaluate_value_str(class_name + base.SET_REQ)()
        rep = _evaluate_value_str(class_name + base.SET_REP)()
        reqrep = base.NanonisReqRep(req, rep)
        reqrep_map[class_name] = reqrep
    return reqrep_map


@dataclass
class SetupProperties:
    """Setup properties tied to scan/spectroscopy saving.

    This merges 'important' properties from three different Nanonis
    messages: ScanPropsSet/Get, ZSpectrPropsSet/Get, BiasSpectrPropsSet/Get.

    NOTE:
    - The attributes are of type SettingState, not boolean!
    - All are defaulted to NO_CHANGE.
    """

    scan_auto_save: base.SettingState = base.NO_CHANGE_VAL
    scan_continuous_scan: base.SettingState = base.NO_CHANGE_VAL
    spec_auto_save: base.SettingState = base.NO_CHANGE_VAL
    spec_save_dialog: base.SettingState = base.NO_CHANGE_VAL
