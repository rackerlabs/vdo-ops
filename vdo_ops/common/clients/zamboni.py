"""
https://resources.rackspace.net/docs#section/Getting-started/Quick-start:-CLI-SDK-tools
"""
from typing import Any, List, Dict, Tuple, Optional

from common import log
from common.clients.identity import IdentityAccount, IdentitySession

logger = log.get_logger(__name__)


class Zamboni:
    def __init__(self, endpoint: str, identity_account: IdentityAccount):
        self.__endpoint = endpoint
        self.__identity_account = identity_account

        self.fields = [
            "id",  # This fixes a pagination bug in Zamboni
            "name",
            "location",
            "provider_account_id",
            "body.name",
            "body._rackspace",
            "body._metadata",
            "body.availableField",
            "body.value",
            "body.config.instanceUuid",
            "body.config.uuid",
            "body.guest",
        ]

        self.host_fields = [
            "id",  # This fixes a pagination bug in Zamboni
            "location",
            "resource_id",
            "body.name",
            "body._rackspace",
        ]

        self.services_list = [
            ("com.rackspace.goss.vm.services.os.admin", 1),
            ("com.rackspace.goss.vm.services.monitoring", 2),
            ("com.rackspace.goss.vm.services.patching", 4),
        ]

    def _apply_org_to_metadata(self, vms: List[Dict[str, Any]]) -> None:
        for vm in vms:
            vm["_metadata"]["orgId"] = vm.get("provider_account_id", None)

    def _apply_service_value(self, vms: List[Dict[str, Any]]) -> None:
        for vm in vms:
            result = (
                self._enrolled_in_goss_service(vm, self.services_list[0])
                | self._enrolled_in_goss_service(vm, self.services_list[1])
                | self._enrolled_in_goss_service(vm, self.services_list[2])
            )
            vm["service_value"] = result

    def _enrolled_in_goss_service(
        self, vm: Dict[str, Any], service: Tuple[str, int]
    ) -> int:
        if self._get_custom_attribute_value(vm, service[0]) == "enrolled":
            return service[1]
        return 0

    def _get_custom_attribute_value(self, vm: Dict[str, Any], definition: str) -> Any:
        result = None
        attr = next(
            (
                field
                for field in vm.get("availableField", [])
                if field.get("name", None) == definition
            ),
            None,
        )
        if attr:
            result = next(  # type: ignore
                (
                    val
                    for val in vm.get("value", [])
                    if val.get("key", None) == attr.get("key", None)
                ),
                {},
            ).get("value", None)
        return result

    def get_vms_by_vcenter(self, vcenter: str) -> Optional[List[Dict[str, Any]]]:
        """
        https://resources.rackspace.net/docs#tag/rpcv/paths/~1rpcv~1vsphere~1virtual_machines/get

        :param vcenter:
        :return:
        """
        with IdentitySession(self.__identity_account) as session:
            response = session.get(
                f"{self.__endpoint}/rpcv/vsphere/virtual_machines",
                params={"filters[location]": vcenter, "fields": ",".join(self.fields)},
            )

        if response.status_code == 404:
            return None
        response.raise_for_status()

        # Get the data
        data = response.json().get("data", [])  # type: List[Dict[str, Any]]

        # Apply the GOSS service values
        self._apply_service_value(data)

        # Apply the org ID to metadata
        self._apply_org_to_metadata(data)

        return data

    def get_hyps_by_device_id(self, device_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        https://resources.rackspace.net/docs#tag/managedvirt/paths/~1managedvirt~1vsphere~1host_systems/get
        Note: This call only get managed virt hypervisors.
        (It is likely that they are the only ones with a device ID)
        """
        with IdentitySession(self.__identity_account) as session:
            response = session.get(
                f"{self.__endpoint}/managedvirt/vsphere/host_systems",
                params={
                    "filters[body._rackspace.deviceId]": device_id,
                    "fields": ",".join(self.host_fields),
                },
            )

        if response.status_code == 404:
            return None
        response.raise_for_status()

        # Get the data
        data = response.json().get("data", [])  # type: List[Dict[str, Any]]

        if len(data) == 1:
            return data[0]
        elif len(data) > 1:
            raise Exception(
                f"More than one Hypervisor with device ID {device_id} found"
            )
        else:
            return None
