import logging
import os

import structlog


def get_logger(log_name: str = __name__) -> structlog._config.BoundLoggerLazyProxy:
    """Just stubbed out in case we want later configuration."""
    stagename = os.environ.get("STAGE", "user")
    processors = [
        # This allow logger to have a threadlocal context
        structlog.threadlocal.merge_threadlocal_context,
        # This performs the initial filtering, so we don't
        # evaluate e.g. DEBUG when unnecessary
        structlog.stdlib.filter_by_level,
        # Adds logger=module_name (e.g __main__)
        structlog.stdlib.add_logger_name,
        # Adds level=info, debug, etc.
        structlog.stdlib.add_log_level,
        # Who doesnt like timestamps?
        structlog.processors.TimeStamper(fmt="iso"),
        # Performs the % string interpolation as expected
        structlog.stdlib.PositionalArgumentsFormatter(),
        # Include the stack when stack_info=True
        structlog.processors.StackInfoRenderer(),
        # Include the exception when exc_info=True
        # e.g log.exception() or log.warning(exc_info=True)'s behavior
        structlog.processors.format_exc_info,
    ]

    if stagename in ["dev", "prod"]:
        processors.extend(
            [
                # Decodes the unicode values in any kv pairs
                structlog.processors.UnicodeDecoder(),
                # Creates the necessary args, kwargs for log()
                structlog.processors.JSONRenderer(indent=2, sort_keys=True),
            ]
        )
    else:
        processors.append(
            # All the pretty colors
            structlog.dev.ConsoleRenderer()
        )
    structlog.configure(
        processors=processors,
        # Our "event_dict" is explicitly a dict
        # There's also structlog.threadlocal.wrap_dict(dict) in some examples
        # which keeps global context as well as thread locals
        context_class=dict,
        # Provides the logging.Logger for the underlaying log call
        logger_factory=structlog.stdlib.LoggerFactory(),
        # Provides predefined methods - log.debug(), log.info(), etc.
        wrapper_class=structlog.stdlib.BoundLogger,
        # Caching of our logger
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=logging.DEBUG)
    logger = structlog.wrap_logger(logging.getLogger(log_name))
    logger.setLevel(logging.DEBUG)  # Good old aws screwing things up
    return logger


logger = get_logger()
