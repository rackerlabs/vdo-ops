import socket
import threading
from contextlib import contextmanager
from typing import Tuple, Any, Iterator, List

from pyVim import connect
from pyVmomi import vim
from pyVmomi.VmomiSupport import ManagedObject

from common import log
from common.utils import util

socket.setdefaulttimeout(15)  # Lambda max execution time is 20
logger = log.get_logger(__name__)


class VmwareClient:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 443,
        si: vim.ServiceInstance = None,
    ):
        self.__host = host
        self.__username = username
        self.__password = password
        self.__port = port
        self.__local_data = threading.local()
        self.__local_data.si = si

    def get_datacenter_by(self, datacenter_name: str) -> vim.Datacenter:
        """
        Get the datacenter by its name

        :param datacenter_name: datacenter name
        :return:
        """
        entities = self.__local_data.si.RetrieveContent().rootFolder.childEntity

        datacenters = [
            entity for entity in entities if isinstance(entity, vim.Datacenter)
        ]

        datacenter = next(dc for dc in datacenters if dc.name == datacenter_name)

        logger.debug(f"Found the datacenter: {datacenter is not None}")

        return datacenter

    def get_cluster_by(
        self, datacenter_name: str, cluster_name: str
    ) -> vim.ClusterComputeResource:
        """
        Get cluster by its name

        :param datacenter_name: Datacenter name
        :param cluster_name: cluster name
        :return:
        """
        datacenter = self.get_datacenter_by(datacenter_name)

        clusters = [
            entity
            for entity in datacenter.hostFolder.childEntity
            if isinstance(entity, vim.ClusterComputeResource)
        ]

        cluster = next(x for x in clusters if x.name == cluster_name)

        logger.debug(f"Found the cluster: {cluster is not None}")

        return cluster

    def submit_task_add_host_to_vcenter(
        self,
        host_ip: str,
        host_username: str,
        host_password: str,
        cluster: vim.ClusterComputeResource,
    ) -> str:
        """
        Add the host to the vcenter

        :param host_ip:
        :param host_username:
        :param host_password:
        :param cluster:
        :return: task key
        """
        host_connect_spec = vim.host.ConnectSpec()
        host_connect_spec.hostName = host_ip
        host_connect_spec.userName = host_username
        host_connect_spec.password = host_password
        host_connect_spec.sslThumbprint = util.get_ssl_thumbprint(host_ip)

        add_host_task = cluster.AddHost(spec=host_connect_spec, asConnected=True)

        task_key = add_host_task.info.key  # type: str

        logger.debug("Started the add host task")

        return task_key

    def get_task_info(self, task_key: str) -> Tuple[bool, Any]:
        """
        Get the task info

        :param si: service instance
        :param task_key: task key
        :return: (is_done, error_msg)
        """
        task = vim.Task(task_key)
        task._stub = self.__local_data.si._stub

        state = task.info.state

        logger.debug(f"The state of task {task_key} is {state}")

        if state == vim.TaskInfo.State.success:
            return True, None

        if state == vim.TaskInfo.State.error:
            error_msg = task.info.error.msg  # type: str

            logger.debug(f"Got the error: {error_msg}")

            return True, error_msg

        return False, None

    def get_current_time(self) -> str:
        """
        Return the current time

        :return: Current time
        """
        return str(self.__local_data.si.CurrentTime())

    def datacenter_exists(self, datacenter_name: str) -> bool:
        """
        Check if specific datacenter exists or not

        :param datacenter_name:
        :return:
        """
        entities = self.__local_data.si.RetrieveContent().rootFolder.childEntity

        datacenters = [
            entity for entity in entities if isinstance(entity, vim.Datacenter)
        ]

        return any(dc.name == datacenter_name for dc in datacenters)

    def add_datacenter(self, datacenter_name: str) -> None:
        """
        Create the datacenter object inside the vcenter

        :param datacenter_name: Datacenter name
        :return:
        """
        folder = self.__local_data.si.RetrieveContent().rootFolder

        if folder is not None and isinstance(folder, vim.Folder):
            folder.CreateDatacenter(name=datacenter_name)
        else:
            raise Exception("Not able to create datacenter")

    def cluster_exists(self, cluster_name: str, datacenter: vim.Datacenter) -> bool:
        """
        Check if specific cluster exist in the target datacenter or not

        :param cluster_name:
        :param datacenter:
        :return:
        """
        clusters = [
            entity
            for entity in datacenter.hostFolder.childEntity
            if isinstance(entity, vim.ClusterComputeResource)
        ]

        return any(cluster.name == cluster_name for cluster in clusters)

    def add_cluster(self, cluster_name: str, datacenter: vim.Datacenter) -> None:
        """
        Create the cluster inside the datacenter object

        :param datacenter: Datacenter
        :param cluster_name: cluster name
        :return:
        """
        datacenter.hostFolder.CreateClusterEx(
            name=cluster_name, spec=vim.cluster.ConfigSpecEx()
        )

    def init_connection(self) -> None:
        """
        Initiate the connection

        :return:
        """
        logger.debug("Opening session")

        self.__local_data.si = connect.SmartConnectNoSSL(
            host=self.__host,
            user=self.__username,
            pwd=self.__password,
            port=self.__port,
        )

        logger.debug("Session is granted")

    def close_connection(self) -> None:
        """
        Close the connection

        :return:
        """
        logger.debug("Closing session")

        connect.Disconnect(self.__local_data.si)
        self.__local_data.si = None

        logger.debug("Session is closed")

    @contextmanager
    def open_session(self) -> Iterator[Any]:
        """
        Create a vim.ServiceInstance instance and inject it to the client itself.
        Disconnect the session once the action is done

        :return:
        """
        self.init_connection()

        try:
            yield self
        finally:
            self.close_connection()

    def add_license(self, license_key: str) -> None:
        """
        Add license key

        :param license_key: license key
        :return:
        """
        license_manager = self.__local_data.si.RetrieveContent().licenseManager
        license_manager.AddLicense(licenseKey=license_key)

    def update_zamboni_permission(self) -> None:
        """
        Update zamboni user to have read only permission on vcenter

        :return:
        """
        manager = self.__local_data.si.RetrieveContent().authorizationManager
        root_folder = self.__local_data.si.RetrieveContent().rootFolder
        zamboni_read_only_permission = vim.AuthorizationManager.Permission(
            entity=root_folder,
            group=False,
            principal="zamboni@vsphere.local",
            propagate=True,
            roleId=-2,
        )
        manager.SetEntityPermissions(
            entity=root_folder, permission=[zamboni_read_only_permission]
        )

    def get_host_systems(
        self, datacenter_name: str, cluster_name: str
    ) -> List[ManagedObject]:
        cluster = self.get_cluster_by(datacenter_name, cluster_name)

        return list(cluster.host)
