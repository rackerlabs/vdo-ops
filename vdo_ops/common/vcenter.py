import socket
from functools import wraps
from typing import Any

import requests
from defusedxml import ElementTree
from pyVmomi import vim

from common import log
from common.clients.vmware import VmwareClient

socket.setdefaulttimeout(15)  # Lambda max execution time is 20

logger = log.get_logger(__name__)


class VcenterException(Exception):
    pass


class TaskFailureException(VcenterException):
    pass


class Vcenter:
    __DATACENTER_NAME = "Datacenter"
    __CLUSTER_NAME = "cluster"

    def __init__(
        self, vcenter_host: str, vsphere_username: str, vsphere_password: str
    ) -> None:
        self.__vmware_client = VmwareClient(
            vcenter_host, vsphere_username, vsphere_password
        )
        self.vcenter_host = vcenter_host

    def _open_session(f: Any) -> Any:
        @wraps(f)
        def wrapped(instance: Any, *args: Any, **kwargs: Any) -> Any:
            with instance.__vmware_client.open_session():
                return f(instance, *args, **kwargs)

        return wrapped

    @_open_session
    def submit_task_add_host(
        self, host_ip: str, host_username: str, host_password: str
    ) -> str:
        """
        Submit a task to add the host to the vcenter

        :param host_ip:
        :param host_username:
        :param host_password:
        :return:
        """
        logger.info(f"Submitting the request to add the host {host_ip} to vcenter")

        cluster = self.__vmware_client.get_cluster_by(
            Vcenter.__DATACENTER_NAME, Vcenter.__CLUSTER_NAME
        )

        task_key = self.__vmware_client.submit_task_add_host_to_vcenter(
            host_ip, host_username, host_password, cluster
        )

        logger.info(f"Got the task key returned: {task_key}")

        return task_key

    @_open_session
    def is_task_done(self, task_key: str) -> bool:
        """
        Check if the task is done correctly or not.
        Raise a TaskFailureException if the task failed

        :param task_key:
        :return:
        """
        logger.info(f"Checking if the task {task_key} is done or not")

        is_task_done, error_msg = self.__vmware_client.get_task_info(task_key)

        if is_task_done is True and error_msg is not None:
            logger.error(f"Task {task_key} failed: {error_msg}")

            raise TaskFailureException(f"Task {task_key} was failed: {error_msg}")
        else:
            logger.info(f"Task {task_key} is done? {is_task_done}")

            return is_task_done

    def reach_vsphere_api(self) -> bool:
        """
        Reach the vsphere api on vcenter.

        :return: True/False
        """
        logger.info("Checking whether the vcenter vsphere API is reachable or not")
        try:
            logger.info("Checking if vcenter is working or not")
            with self.__vmware_client.open_session():
                self.__vmware_client.get_current_time()
        except ConnectionRefusedError:
            logger.exception("Vcenter is not online yet")
            return False
        except Exception as e:
            if "is not a VIM server" in str(e) or "timed out" in str(e):
                logger.exception("Vcenter is still starting")
                return False
            else:
                logger.exception("Unexpected exception happened")
                raise e

        logger.info("Checking if vcenter UI is alive or not")
        is_ui_alive = self._is_ui_alive()

        logger.info("UI is alive?", is_ui_alive=is_ui_alive)

        return is_ui_alive

    def _is_ui_alive(self) -> bool:
        url = f"https://{self.vcenter_host}/ui/healthstatus"
        resp = requests.get(url, verify=False)  # nosec
        try:
            xml_tree = ElementTree.fromstring(resp.content)
        except ElementTree.ParseError:
            logger.exception(
                "UI is not alive since application could not get a valid xml from "
                "vcenter healthstatus check"
            )
            return False

        status_code = resp.status_code
        status = xml_tree[0].text

        good_response = status_code == 200
        good_status = status == "GREEN"

        is_healthy = good_response and good_status

        logger.debug(
            "vcenter status",
            status_code=status_code,
            status=status,
            is_healthy=is_healthy,
        )

        return is_healthy

    def is_accessible(self) -> bool:
        try:
            logger.info("Checking if vcenter is accessible or not")

            with self.__vmware_client.open_session():
                self.__vmware_client.get_current_time()
        except ConnectionRefusedError:
            logger.exception(
                "Not able to connect to vcenter since connection was refused"
            )

            return False
        except socket.gaierror:
            logger.exception("It seems it is not a valid vcenter")

            return False
        except vim.fault.InvalidLogin:
            logger.exception("Not able to connect to vcenter due to wrong credentials")

            return False
        except Exception as e:
            if "is not a VIM server" in str(e):
                logger.exception("It seems it is not a valid vcenter")

                return False
            elif "timed out" in str(e):
                logger.exception(
                    "Not able to connect to vcenter due to timed out connection"
                )

                return False
            else:
                logger.exception(
                    "Caught unexpected exception. Assume it is caused by failed "
                    "connection. This needs investigation"
                )

                return False

        return True

    @_open_session
    def create_datacenter(self) -> None:
        """
        Create the datacenter inside the current vcenter if it does not exist.

        :return:
        """
        logger.info(
            f"Creating the datacenter {Vcenter.__DATACENTER_NAME} inside vcenter"
        )

        if self.__vmware_client.datacenter_exists(Vcenter.__DATACENTER_NAME):
            logger.info("Datacenter was already created. Skip current step")
            return

        self.__vmware_client.add_datacenter(Vcenter.__DATACENTER_NAME)

    @_open_session
    def create_cluster(self) -> None:
        """
        Create the cluster inside the current vcenter's datacenter if it does not exist.

        :return:
        """
        logger.info(
            f"Creating the cluster {Vcenter.__CLUSTER_NAME} "
            f"under datacenter {Vcenter.__DATACENTER_NAME} inside vcenter"
        )

        datacenter = self.__vmware_client.get_datacenter_by(Vcenter.__DATACENTER_NAME)

        if self.__vmware_client.cluster_exists(Vcenter.__CLUSTER_NAME, datacenter):
            logger.info("Cluster was already created. Skip current step")
            return

        self.__vmware_client.add_cluster(Vcenter.__CLUSTER_NAME, datacenter)

    @_open_session
    def add_license(self, license_key: str) -> None:
        self.__vmware_client.add_license(license_key)

    @_open_session
    def update_zamboni_permission(self) -> None:
        self.__vmware_client.update_zamboni_permission()

    @_open_session
    def get_number_of_hosts(self) -> int:
        return len(
            self.__vmware_client.get_host_systems(
                Vcenter.__DATACENTER_NAME, Vcenter.__CLUSTER_NAME
            )
        )
