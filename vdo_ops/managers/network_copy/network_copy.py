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
    hostname = event.get("hostname", None)
    logger.bind(
        from_device=from_device_number, to_device=to_device_number, vcenter=hostname
    )

    vsphere_api = _get_vsphere_api(hostname)

    # Get the vms in the vCenter from Zamboni
    from_hyp = CLIENTS.zamboni_client.get_hyps_by_device_id(from_device_number)
    to_hyp = CLIENTS.zamboni_client.get_hyps_by_device_id(to_device_number)

    # Make the call to copy networks
    vsphere_api.copy_networks(from_hyp.get("name", None), to_hyp.get("name", None))

    logger.debug("Network copy complete.")
