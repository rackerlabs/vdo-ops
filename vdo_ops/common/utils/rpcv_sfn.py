from functools import partial, wraps
from types import ModuleType
from typing import Callable, Any

import structlog

from common import log

logger = log.get_logger(__file__)

RPCV_TASK_SKIP_URL = "rpcv-skip"


def get_called_func(
    action: str, target_module: ModuleType, sfn_event: Any
) -> Callable[..., Any]:
    """
    Find the function to be executed and return it with correct argument value from
    step function event dict

    We are expecting:
    1) action defined in step function YAML == python function name
    2) parameter defined in step function YAML == python function argument name

    :param action:
    :param target_module:
    :param sfn_event:
    :return:
    """
    if any(func_name == action for func_name in dir(target_module)) is False:
        logger.error("Bad Action Called", target_action=action)

        raise AttributeError(f"Unsupported action called: {action}")

    action_func = getattr(target_module, action)

    action_arg_names = action_func.__code__.co_varnames[
        : action_func.__code__.co_argcount
    ]

    available_keys = sfn_event.keys()

    non_existing_args = list(
        filter(lambda arg_name: arg_name not in available_keys, action_arg_names)
    )

    if len(non_existing_args) > 0:
        raise AttributeError(f"Unsupported action args: {non_existing_args}")

    action_args = tuple(map(lambda arg_name: sfn_event.get(arg_name), action_arg_names))

    called_func = partial(action_func, *action_args)

    return called_func


def rpcv_sfn_logger(func: Any) -> Any:
    """
    Register job id into logger context and clean up context after step function is done
    :param func:
    :return:
    """

    @wraps(func)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            job_id = args[0].get("job_id")

            if job_id is not None:
                structlog.threadlocal.bind_threadlocal(job_id=job_id)

            return func(*args, **kwargs)
        finally:
            logger.debug("Cleaning logging context")

            structlog.threadlocal.clear_threadlocal()

    return wrapped
