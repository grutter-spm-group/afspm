"""Holds asylum controller action handling."""

import logging

from ... import actions
from . import sxm


logger = logging.getLogger(__name__)


class SXMActionHandler(actions.ActionHandler):
    """Implements SXM-specific aciton handling.

    Attributes:
        client: DDE client, used to communicate with the SXM controller.
    """

    def __init__(self, client: sxm.DDEClient, **kwargs):
        """Init our SXM handler, feeding the DDE Client."""
        if client is None:
            msg = "No client provided, cannot continue!"
            logger.critical(msg)
            raise AttributeError(msg)

        self.client = client
        super().__init__(**kwargs)


def request_action(handler: SXMActionHandler, method_name: str,
                   params: tuple[float | str] | None = None):
    """Request an action from SXM.

    Args:
        handler: the action handler we use to request.
        method_name: the name of the Asylum method we are calling.
        params: additional parameters to pass (as a tuple).

    Raises:
        actions.ActionError if the request fails for any reason.
    """
    method_call = method_name
    if params:
        method_call += '('
        for param in params:
            if isinstance(param, str):
                method_call += "'" + param + "'"
            else:
                method_call += str(param)
            method_call += ','
        method_call = method_call[0:-1]  # Remove last ,
        method_call += ');'
    logger.trace(f'method_call: {method_call}')

    try:
        handler.client.execute_no_return(method_call)
    except sxm.RequestError as e:
        msg = f'SXM: Calling {method_name} with args {params} failed: {e}'
        logger.error(msg)
        raise actions.ActionError(msg)
