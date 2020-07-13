import socket
from functools import wraps
from typing import Any

from common import log
from common.clients.vsphere import VsphereClient

socket.setdefaulttimeout(15)  # Lambda max execution time is 20

logger = log.get_logger(__name__)


class VsphereApi:
    def __init__(self, hostname):
        self.client = VsphereClient(hostname)

    def _open_session(f: Any) -> Any:
        @wraps(f)
        def wrapped(instance: Any, *args: Any, **kwargs: Any) -> Any:
            with instance.client.open_session():
                return f(instance, *args, **kwargs)

        return wrapped

    @_open_session
    def copy_networks(self, from_device_name, to_device_name):
        """
        For the give source and destination devices, copies the network info
        from the source device to the destination device in the vCenter.
        """
        logger.info(
            f"Beginning network copy from {from_device_name} to {to_device_name}"
        )

        from_switches = self.client.get_host_virtual_switches(from_device_name)

        for from_switch in from_switches:
            logger.info(f"Checking vSwitch: {from_switch.name}")

            if self.client.has_virtual_switch(to_device_name, from_switch.name):
                logger.info("vSwitch already exists on destination.")
            else:
                logger.info("Adding vSwitch to destination.")
                self.client.add_host_vswitch(
                    to_device_name, from_switch.name, from_switch.spec
                )

            for from_portgroup in self.client.get_portgroup_by_vswitch(
                from_device_name, from_switch.name
            ):
                logger.info(f"Checking portgroup: {from_portgroup.spec.name}")

                if self.client.is_in_do_cot_copy_lsit(
                    from_device_name, from_portgroup.spec.name
                ):
                    logger.info("Portgroup is in do not copy list.")
                    continue

                if self.client.has_portgroup(to_device_name, from_portgroup.spec.name):
                    logger.info("Portgroup already exists on destination.")
                else:
                    logger.info("Adding portgroup to destination.")
                    self.client.add_host_portgroup(to_device_name, from_portgroup.spec)

        logger.info("Network copy complete.")
