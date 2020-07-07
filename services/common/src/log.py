import logging
import os

from fleece import log


def setup_logging():
    log.setup_root_logger()
    level = logging.getLevelName(os.environ.get("LOG_LEVEL", "info").upper())
    logger = log.get_logger(level=level)
    logging.getLogger("boto").setLevel(logging.CRITICAL)
    logging.getLogger("boto3").setLevel(logging.CRITICAL)
    logging.getLogger("botocore").setLevel(logging.CRITICAL)
    return logger
