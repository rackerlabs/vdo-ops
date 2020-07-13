import socket
import threading
from contextlib import contextmanager

from pyVim import connect
from pyVmomi import vim

from common import log, secrets

socket.setdefaulttimeout(15)  # Lambda max execution time is 20
logger = log.get_logger(__name__)

AUTOMATION_ADMIN_USERNAME = secrets.get_parameter(
    "/vdo/global/vsphere_admin_automation_username"
)
AUTOMATION_ADMIN_PASSWORD = secrets.get_parameter(
    "/vdo/global/vsphere_admin_automation_password"
)


class VsphereClient:
    def __init__(self, host_name: str, si: vim.ServiceInstance = None):
        self.__host = host_name
        self.__local_data = threading.local()
        self.__local_data.si = si

    def init_connection(self) -> None:
        logger.debug("Opening session")
        self.__local_data.si = connect.SmartConnectNoSSL(
            host=self.__host,
            user=AUTOMATION_ADMIN_USERNAME,
            pwd=AUTOMATION_ADMIN_PASSWORD,
            port=443,
        )
        logger.debug("Session is granted")

    def close_connection(self) -> None:
        logger.debug("Closing session")
        connect.Disconnect(self.__local_data.si)
        self.__local_data.si = None
        logger.debug("Session is closed")

    @contextmanager
    def open_session(self):
        self.init_connection()
        try:
            yield self
        finally:
            self.close_connection()

    def _get_obj(self, vimtype, name):
        """
        Get the vsphere object associated with a given text name
        """
        content = self.__local_data.si.RetrieveContent()
        container = content.viewManager.CreateContainerView(
            content.rootFolder, [vimtype], True
        )
        obj = None
        for c in container.view:
            if c.name == name:
                obj = c
                break
        return obj

    # HOST SYSTEM
    def get_host_system(self, name):
        """
        Gets the Host System which mathces the given name.
        """
        return self._get_obj(vim.HostSystem, name)

    def get_host_portgroups(self, host_name):
        """
        Gets all the portgroups for a given host system name.
        """
        return self._get_obj(vim.HostSystem, host_name).config.network.portgroup

    def get_host_virtual_switches(self, host_name):
        """
        Gets all the virtual switches for a given host system name.
        """
        return self._get_obj(vim.HostSystem, host_name).config.network.vswitch

    def get_portgroup_by_vswitch(self, host_name, vswitch_name):
        """
        For a given host system, finds the port group that has the given virtual switch.
        """
        host = self.get_host_system(host_name)

        portgroup_list = []

        for portgroup in host.config.network.portgroup:
            if (
                portgroup.vswitch is not None
                and portgroup.vswitch.split("-")[2] == vswitch_name
            ):
                portgroup_list.append(portgroup)

        return portgroup_list

    def get_do_not_copy_list(self, host_name):
        """
        Makes a list of all virtual nics and console virtual
        nics for a given host system.
        """
        host = self.get_host_system(host_name)
        return [*host.config.network.vnic, *host.config.network.consoleVnic]

    def is_in_do_cot_copy_lsit(self, host_name, portgroup_name):
        """
        Checks to see if the given port group is in the do not
        copy list of the given host.
        """
        return [
            vnic
            for vnic in self.get_do_not_copy_list(host_name)
            if vnic.portgroup == portgroup_name
        ]

    def has_virtual_switch(self, host_name, vswitch_name):
        """
        Checks to see if the given host system has the given virtual switch.
        """
        host = self.get_host_system(host_name)
        return [
            vswitch
            for vswitch in host.config.network.vswitch
            if vswitch.name == vswitch_name
        ]

    def has_portgroup(self, host_name, portgroup_name):
        """
        Checks to see if the given host system has the given port group.
        """
        host = self.get_host_system(host_name)
        return [
            portgroup
            for portgroup in host.config.network.portgroup
            if portgroup.spec.name == portgroup_name
        ]

    def add_host_vswitch(self, host_name, vswitch_name, vswitch_spec):
        """
        Adds the given virtual switch to the host system.
        """
        host = self.get_host_system(host_name)
        host.configManager.networkSystem.AddVirtualSwitch(vswitch_name, vswitch_spec)

    def add_host_portgroup(self, host_name, portgroup_spec):
        """
        Adds the given port group to the given host system.
        """
        host = self.get_host_system(host_name)
        host.configManager.networkSystem.AddPortGroup(portgroup_spec)
