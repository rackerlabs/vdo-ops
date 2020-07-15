from common import log
from common.constants import CLIENTS
from common.vsphere_api import VsphereApi

logger = log.get_logger(__name__)


def _get_vsphere_api(hostname):
    return VsphereApi(hostname)


def handler(event, context):
    logger.debug("Beginning network copy!")
    from_device_number = event.get("from_device", None)
    to_device_number = event.get("to_device", None)
    logger.bind(from_device=from_device_number, to_device=to_device_number)

    # Get the vms in the vCenter from Zamboni
    from_hyp = CLIENTS.zamboni_client.get_hyps_by_device_id(from_device_number)
    to_hyp = CLIENTS.zamboni_client.get_hyps_by_device_id(to_device_number)

    hostname = from_hyp.get("location", None)
    # Make the call to copy networks
    try:
        vsphere_api = _get_vsphere_api(hostname)
    except Exception as e:
        logger.error(f"There was an error connecting to {hostname}.", e)
        raise Exception(f"There was an error connecting to {hostname}. {str(e)}")

    try:
        vsphere_api.copy_networks(from_hyp.get("name", None), to_hyp.get("name", None))
    except Exception as e:
        logger.error("There was an error during the network copy process.", e)
        raise Exception(f"There was an error during the network copy process. {str(e)}")

    logger.debug("Network copy complete.")
