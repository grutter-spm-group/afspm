"""Holds asylum controller action handling."""

import logging
from afspm.components.microscope import actions

from sxm import DDEClient


logger = logging.getLogger(__name__)


class SXMActionHandler(actions.ActionHandler):
    """Implements SXM-specific aciton handling.

    Attributes:
        client: DDE client, used to communicate with the SXM controller.
    """

    def __init__(self, client: DDEClient, **kwargs):
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
    try:
        success, __ = handler.client.SendWait(method_name, params)
        if success:
            return
        else:
            logger.info('Did not receive response from DDE client for '
                        f'{method_name}, with {params}.')
    except actions.ActionError:
        pass

    msg = f'SXM: Calling {method_name} with args {params} failed.'
    logger.error(msg)
    raise actions.ActionError(msg)
