from common import log

logger = log.get_logger(__name__)


def handler(event, context):
    logger.debug("Handler called.")
    return
