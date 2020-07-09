import os
from collections import namedtuple
from typing import Dict, Any, List, Optional

import requests
from lxml.objectify import ObjectifiedElement  # nosec
from pyvcloud.vcd.client import (
    BasicLoginCredentials,
    TaskStatus,
    EdgeGatewayType,
    EntityType,
)
from pyvcloud.vcd.client import Client, RelationType
from pyvcloud.vcd.exceptions import EntityNotFoundException, BadRequestException
from pyvcloud.vcd.firewall_rule import FirewallRule
from pyvcloud.vcd.gateway import Gateway
from pyvcloud.vcd.org import Org
from pyvcloud.vcd.static_route import StaticRoute
from pyvcloud.vcd.system import System
from pyvcloud.vcd.vdc import VDC

from common import secrets, log, constants
from common.clients.vm_extended import VmExtended
from common.exceptions.vcd import TaskFailureException
from common.exceptions.vcd import (
    UnknownRegionError,
    OrganizationAlreadyExistException,
    OrganizationNotFoundException,
    UnknownResourceError,
)

# TODO remove this code once the issue with getLogger of
#  VAPP in pyvcloud library is resolved.

obsolete_path = os.getcwd()
os.chdir("/tmp")
from pyvcloud.vcd.vapp import VApp  # noqa: E402

os.chdir(obsolete_path)

requests.packages.urllib3.disable_warnings()  # type: ignore

REGIONS: Dict[str, Any] = secrets.get_secrets_from_ssm("regions")

VcdOrganization = namedtuple("VcdOrganization", ["id", "name", "desc"])

logger = log.logger


def get_creds(rax_endpoint: str) -> Dict[str, str]:
    endpoint_info = {}
    for k, v in REGIONS.items():
        if k.startswith(f"{rax_endpoint}/"):
            fixed_name = k.replace(f"{rax_endpoint}/", "")
            endpoint_info[fixed_name] = v
    return endpoint_info


def create_client(endpoint: str, username: str, password: str) -> Client:
    client = Client(
        endpoint,
        verify_ssl_certs=False,
        log_file="/dev/null",
        log_requests=False,
        log_headers=False,
        log_bodies=False,
    )

    client.set_credentials(BasicLoginCredentials(username, "System", password))

    return client


class VcloudClient:
    def __init__(self, vcd_region: str) -> None:
        vcd_info = get_creds(vcd_region)
        if vcd_info == {}:
            raise UnknownRegionError(f"Invalid Region: {vcd_region}")

        self.__client = create_client(
            vcd_info["endpoint"], vcd_info["username"], vcd_info["password"]
        )

    def __create_system(self) -> System:
        return System(self.__client, admin_resource=self.__client.get_admin())

    def get_org(self, org_name: str) -> VcdOrganization:
        org_resource = self.__client.get_org_by_name(org_name)

        return VcloudClient.__extract_org_info(org_resource)

    @staticmethod
    def __extract_org_info(org_resource: ObjectifiedElement) -> VcdOrganization:
        org_id = org_resource.get("id").split(":")[-1]
        return VcdOrganization(
            id=org_id, name=org_resource.get("name"), desc=org_resource.FullName
        )

    def create_org(self, org_name: str, org_full_name: str) -> VcdOrganization:
        """ Create a new organization
        :param org_name: name of the organization that is identical in vcd
        :param org_full_name: full name of organization
        :return: newly created org
        """
        if self.__org_exists(org_name):
            raise OrganizationAlreadyExistException(
                f"Organization {org_name} is already created"
            )

        try:
            org_resource = self.__create_system().create_org(
                org_name, org_full_name, True
            )
        except BadRequestException as e:
            if str(e).startswith("Status code: 400/DUPLICATE_NAME"):
                raise OrganizationAlreadyExistException(
                    f"Organization {org_name} is already created"
                )
            else:
                raise e

        return VcloudClient.__extract_org_info(org_resource)

    def org_exists(self, org_name: str) -> bool:
        return self.__org_exists(org_name)

    def __org_exists(self, org_name: str) -> bool:
        try:
            self.__client.get_org_by_name(org_name)
            return True
        except EntityNotFoundException:
            return False

    def delete_org(self, org_name: str) -> None:
        """ Delete an organization

        :param org_name: name of the organization that is identical in vcd
        :return:
        """
        if not self.__org_exists(org_name):
            raise OrganizationAlreadyExistException(
                f"Organization {org_name} is already created"
            )

        try:
            self.__create_system().delete_org(org_name, force=True, recursive=True)
        except EntityNotFoundException:
            raise OrganizationNotFoundException(f"Organization {org_name} is not found")

    def vdc_exists(self, org_name: str, vdc_name: str) -> bool:
        org = self.__get_org(org_name)

        return org.get_vdc(vdc_name) is not None

    def create_vdc(
        self,
        org_name: str,
        storage_profile_name: str,
        vdc_name: str,
        pvdc_name: str,
        network_pool_name: str,
    ) -> str:
        org_resource = self.__client.get_org_by_name(org_name)

        org = Org(self.__client, resource=org_resource)

        storage_profile = {
            "name": storage_profile_name,
            "enabled": True,
            "units": "MB",
            "limit": 1_535_243,
            "default": True,
        }

        task = org.create_org_vdc(
            vdc_name,
            pvdc_name,
            "Testing VDC creation",
            storage_profiles=[storage_profile],
            network_quota=1000,
            network_pool_name=network_pool_name,
        )

        task_href = VcloudClient.__extract_task_href(task)

        logger.debug(
            "Submitted the request to create a vdc",
            vdc_name=vdc_name,
            task_href=task_href,
        )

        return task_href

    def network_exists(self, org_name: str, vdc_name: str) -> bool:
        vcsa_network_name = f"{vdc_name}_network"

        vdc = self.__get_vdc(org_name, vdc_name)

        try:
            vdc.get_routed_orgvdc_network(vcsa_network_name)
        except EntityNotFoundException:
            logger.exception(
                "It looks like network is not created yet", network=vcsa_network_name
            )
            return False

        return True

    def update_network(
        self,
        vdc_name: str,
        org_name: str,
        ip_block: str,
        starting_ip: str,
        ending_ip: str,
    ) -> str:
        vcsa_network_name = f"{vdc_name}_network"
        edge_gateway_name = f"{vdc_name}-edge"

        org_resource = self.__client.get_org_by_name(org_name)
        vdc_resource = Org(self.__client, resource=org_resource).get_vdc(vdc_name)
        vdc = VDC(self.__client, resource=vdc_resource)

        task = vdc.create_routed_vdc_network(
            vcsa_network_name,
            edge_gateway_name,
            ip_block,
            ip_range_start=starting_ip,
            ip_range_end=ending_ip,
        )

        task_href = VcloudClient.__extract_task_href(task)

        logger.debug(
            "Submitted the request to update network on vdc",
            network=vcsa_network_name,
            task_href=task_href,
        )

        return task_href

    def vapp_exists(self, org_name: str, vdc_name: str, vapp_name: str) -> bool:
        vdc = self.__get_vdc(org_name, vdc_name)
        try:
            vdc.get_vapp(vapp_name)
        except EntityNotFoundException:
            logger.exception("It looks like vApp is not created yet", vapp=vapp_name)

            return False

        return True

    def create_vapp(
        self,
        org_name: str,
        vdc_name: str,
        vapp_name: str,
        catalog_name: str,
        vapp_template_name: str,
        network_name: str,
        vm_name: str,
        vm_ip: str,
    ) -> str:
        org = Org(
            client=self.__client, resource=self.__client.get_org_by_name(org_name)
        )
        vdc = VDC(client=self.__client, resource=org.get_vdc(name=vdc_name))

        task = vdc.instantiate_vapp(
            name=vapp_name,
            catalog=catalog_name,
            template=vapp_template_name,
            description="This is a new vcsa vapp from the old one.",
            network=network_name,
            ip_allocation_mode="manual",
            deploy=False,
            power_on=False,
            accept_all_eulas=True,
            memory=None,
            cpu=None,
            disk_size=None,
            password=None,
            cust_script=None,
            vm_name=vm_name,
            hostname=None,
            ip_address=vm_ip,
            storage_profile=None,
            network_adapter_type="VMXNET3",
        )

        task_href = VcloudClient.__extract_task_href(task)

        logger.debug(
            "Submitted the request to create a vApp",
            vcenter=vapp_name,
            task_href=task_href,
        )

        return task_href

    def edge_gateway_exists(self, org_name: str, vdc_name: str) -> bool:
        edge_gateway_name = f"{vdc_name}-edge"

        vdc = self.__get_vdc(org_name, vdc_name)

        return vdc.get_gateway(edge_gateway_name) is not None

    def create_edge_gateWay(self, org_name: str, vdc_name: str) -> str:
        org = Org(
            client=self.__client, resource=self.__client.get_org_by_name(org_name)
        )
        vdc = VDC(client=self.__client, resource=org.get_vdc(name=vdc_name))

        edge_gateway_name = f"{vdc_name}-edge"

        task = vdc.create_gateway_api_version_32(
            edge_gateway_name,
            external_networks=["VCD-EDGES"],
            is_default_gateway=True,
            selected_extnw_for_default_gw="VCD-EDGES",
            default_gateway_ip="10.76.5.1",
            edgeGatewayType=EdgeGatewayType.NSXV_BACKED.value,
        )

        task_href = VcloudClient.__extract_task_href(task)

        logger.debug(
            "Submitted the request to create a edge gateway",
            edge_gateway=edge_gateway_name,
            task_href=task_href,
        )

        return task_href

    @staticmethod
    def __extract_task_href(task: ObjectifiedElement) -> str:
        return str(task.Tasks.Task[0].get("href"))

    def check_task(self, href: str) -> bool:
        status = self.__client.get_task_monitor().get_status({"href": href})

        logger.debug("Got status", status=status, task_href=href)

        if status == TaskStatus.SUCCESS.value.lower():
            logger.debug("Task is done", status=status, task_href=href)

            return True
        elif status in [
            TaskStatus.ERROR.value.lower(),
            TaskStatus.ABORTED.value.lower(),
            TaskStatus.CANCELED.value.lower(),
        ]:
            raise TaskFailureException(f"status={status}")
        else:
            return False

    def delete_resources(self, org_name: str, vdc_name: str) -> List[str]:
        """ Delete all resources inside VDC

        :param org_name: name of the organization that is identical in vcd
        :param vdc_name: name of the vdc
        :return:
        """
        try:
            org = Org(
                client=self.__client, resource=self.__client.get_org_by_name(org_name)
            )
        except EntityNotFoundException:
            raise OrganizationNotFoundException(f"Organization {org_name} is not found")

        vdc_resource = org.get_vdc(name=vdc_name)
        task_hrefs: List[str] = []

        if vdc_resource is None:
            return task_hrefs

        vdc = VDC(client=self.__client, resource=org.get_vdc(name=vdc_name))

        for resource in vdc.list_resources():
            if EntityType.VAPP.value == resource["type"]:
                task = vdc.delete_vapp(resource["name"], True)
                task_hrefs.append(task.attrib["href"])
            elif EntityType.DISK.value == resource["type"]:
                task = vdc.delete_disk(resource["name"])
                task_hrefs.append(task.attrib["href"])
            else:
                raise UnknownResourceError(
                    f"Unknown resource of {resource['type']} found in VDC: {vdc_name}"
                )

        return task_hrefs

    def delete_networks(self, org_name: str, vdc_name: str) -> List[str]:
        """ Delete all networks inside VDC

        :param org_name: name of the organization that is identical in vcd
        :param vdc_name: name of the vdc
        :return:
        """
        try:
            org = Org(
                client=self.__client, resource=self.__client.get_org_by_name(org_name)
            )
        except EntityNotFoundException:
            raise OrganizationNotFoundException(f"Organization {org_name} is not found")

        vdc_resource = org.get_vdc(name=vdc_name)
        task_hrefs: List[str] = []

        if vdc_resource is None:
            return task_hrefs

        vdc = VDC(client=self.__client, resource=org.get_vdc(name=vdc_name))

        for network in vdc.list_orgvdc_network_resources():
            task = self.__client.delete_resource(network.attrib["href"], True, True)
            task_hrefs.append(task.attrib["href"])

        return task_hrefs

    def delete_gateways(self, org_name: str, vdc_name: str) -> List[str]:
        """ Delete all gateways inside VDC

        :param org_name: name of the organization that is identical in vcd
        :param vdc_name: name of the vdc
        :return:
        """
        try:
            org = Org(
                client=self.__client, resource=self.__client.get_org_by_name(org_name)
            )
        except EntityNotFoundException:
            raise OrganizationNotFoundException(f"Organization {org_name} is not found")

        vdc_resource = org.get_vdc(name=vdc_name)
        task_hrefs: List[str] = []

        if vdc_resource is None:
            return task_hrefs

        vdc = VDC(client=self.__client, resource=org.get_vdc(name=vdc_name))

        for gateway in vdc.list_edge_gateways():
            task = self.__client.delete_resource(gateway["href"], True, True)
            task_hrefs.append(task.attrib["href"])

        return task_hrefs

    def delete_cluster(self, org_name: str, vdc_name: str) -> None:
        """ Delete cluster

        :param org_name: name of the organization that is identical in vcd
        :param vdc_name: name of the vdc
        :return:
        """
        try:
            org = Org(
                client=self.__client, resource=self.__client.get_org_by_name(org_name)
            )
        except EntityNotFoundException:
            raise OrganizationNotFoundException(f"Organization {org_name} is not found")

        vdc_resource = org.get_vdc(name=vdc_name)

        if vdc_resource is None:
            return

        vdc = VDC(client=self.__client, resource=org.get_vdc(name=vdc_name))

        if vdc.resource.IsEnabled:
            vdc.enable_vdc(False)

        vdc.delete_vdc()

    def add_gateway_nat_rule(
        self,
        org_name: str,
        vdc_name: str,
        original_address: str,
        translated_address: str,
        action: str,
    ) -> None:
        """ This method will add a nat rule at edge gateway level.

        :param org_name: name of the organization that is identical in vcd
        :param vdc_name: name of the vdc
        :param original_address: original address
        :param translated_address: address to be translated
        :param action: snat/dnat
        :return:
        """
        try:
            org = Org(
                client=self.__client, resource=self.__client.get_org_by_name(org_name)
            )
        except EntityNotFoundException:
            raise OrganizationNotFoundException(f"Organization {org_name} is not found")

        vdc = VDC(client=self.__client, resource=org.get_vdc(name=vdc_name))

        edge_gateway = Gateway(
            client=self.__client, resource=vdc.get_gateway(f"{vdc_name}-edge")
        )
        edge_gateway.add_nat_rule(
            action=action,
            original_address=original_address,
            translated_address=translated_address,
        )

        logger.debug(
            f"Created the ${action} nat rule on vcenter",
            original_address=original_address,
            translated_address=translated_address,
        )

    def do_nat_rules_created(self, org_name: str, vdc_name: str,) -> bool:

        try:
            org = Org(
                client=self.__client, resource=self.__client.get_org_by_name(org_name)
            )
        except EntityNotFoundException:
            raise OrganizationNotFoundException(f"Organization {org_name} is not found")

        vdc = VDC(client=self.__client, resource=org.get_vdc(name=vdc_name))

        edge_gateway = Gateway(
            client=self.__client, resource=vdc.get_gateway(f"{vdc_name}-edge")
        )

        nat_rules = edge_gateway.get_nat_rules()

        if not hasattr(nat_rules.natRules, "natRule"):
            logger.debug("There is no nat rule configured yet")

            return False

        snat_found = False
        dnat_found = False
        for natRule in nat_rules.natRules.natRule:
            if natRule.action == constants.SNAT:
                snat_found = True
            if natRule.action == constants.DNAT:
                dnat_found = True

        return snat_found & dnat_found

    def update_guest_properties(
        self,
        org_name: str,
        vdc_name: str,
        vcenter_vapp_name: str,
        vm_name: str,
        vm_ip: str,
        dns_record: str,
        administrator_password: str,
        root_password: str,
        gateway_ip: str,
    ) -> str:
        modified_dns_record = dns_record.rstrip(".")
        org = Org(
            client=self.__client, resource=self.__client.get_org_by_name(org_name)
        )
        vdc = VDC(client=self.__client, resource=org.get_vdc(vdc_name))

        vapp = VApp(client=self.__client, resource=vdc.get_vapp(vcenter_vapp_name))

        vm = VmExtended(client=self.__client, resource=vapp.get_vm(vm_name))

        vm_product_sections_xml = vm.client.get_linked_resource(
            vm.resource, RelationType.DOWN, EntityType.PRODUCT_SECTIONS.value
        )

        vm.update_product_section_property(
            vm_product_sections_xml,
            key="domain",
            class_name="vami",
            instance_name="VMware-vCenter-Server-Appliance",
            value=vm_ip,
            user_configurable=True,
        )
        vm.update_product_section_property(
            vm_product_sections_xml,
            key="guestinfo.cis.appliance.net.dns.servers",
            value="8.8.8.8,8.8.4.4",
            user_configurable=True,
        )
        vm.update_product_section_property(
            vm_product_sections_xml,
            key="guestinfo.cis.appliance.net.pnid",
            value=modified_dns_record,
            user_configurable=True,
        )
        vm.update_product_section_property(
            vm_product_sections_xml,
            key="guestinfo.cis.system.vm0.hostname",
            value=modified_dns_record,
            user_configurable=True,
        )
        vm.update_product_section_property(
            vm_product_sections_xml,
            key="guestinfo.cis.vmdir.password",
            value=administrator_password,
            user_configurable=True,
        )
        vm.update_product_section_property(
            vm_product_sections_xml,
            key="guestinfo.cis.appliance.root.passwd",
            value=root_password,
            user_configurable=True,
        )
        vm.update_product_section_property(
            vm_product_sections_xml,
            key="guestinfo.cis.appliance.net.addr",
            value=vm_ip,
            user_configurable=True,
        )
        vm.update_product_section_property(
            vm_product_sections_xml,
            key="guestinfo.cis.appliance.net.gateway",
            value=gateway_ip,
            user_configurable=True,
        )

        task = vm.send_updated_product_section(vm_product_sections_xml)
        task_href = task.get("href")

        logger.debug(
            "Submitted request to update the VM guest properties",
            vcenter=vcenter_vapp_name,
            vm=vm_name,
            task_href=task_href,
        )
        return str(task_href)

    def is_vapp_powered_on(
        self, org_name: str, vdc_name: str, vcenter_vapp_name: str
    ) -> bool:
        vcenter = self.__get_vapp(org_name, vdc_name, vcenter_vapp_name)

        is_powered_on: bool = vcenter.is_powered_on()

        return is_powered_on

    def power_on_vapp(self, org_name: str, vdc_name: str, vapp_name: str) -> str:
        org = Org(
            client=self.__client, resource=self.__client.get_org_by_name(org_name)
        )
        vdc = VDC(client=self.__client, resource=org.get_vdc(vdc_name))

        vapp = VApp(client=self.__client, resource=vdc.get_vapp(vapp_name))
        task = vapp.power_on()

        task_href = task.get("href")

        logger.debug(
            "Submitted request to power on the vapp",
            vapp=vapp_name,
            task_href=task_href,
        )

        return str(task_href)

    def power_off_vapp(self, org_name: str, vdc_name: str, vapp_name: str) -> str:
        org = Org(
            client=self.__client, resource=self.__client.get_org_by_name(org_name)
        )
        vdc = VDC(client=self.__client, resource=org.get_vdc(vdc_name))

        vapp = VApp(client=self.__client, resource=vdc.get_vapp(vapp_name))
        task = vapp.power_off()

        task_href = task.get("href")

        logger.debug(
            "Submitted request to power off the vapp",
            vapp=vapp_name,
            task_href=task_href,
        )

        return str(task_href)

    def static_route_on_bridge_edge_gateway_exists(
        self, org_name: str, vdc_name: str, vdc_edge_gateway_name: str
    ) -> bool:
        expect_description = f"{org_name}/{vdc_name}/{vdc_edge_gateway_name}"

        bridge_edge_gateway = self.__get_gateway("vdo", "vdo", "BRIDGE-EDGE")

        route_elements: ObjectifiedElement = bridge_edge_gateway.get_static_routes()

        if not hasattr(route_elements.staticRoutes, "route"):
            logger.debug("There is no static route configured yet")

            return False

        route_descriptions: List[str] = list(
            map(
                lambda route: str(route.description),
                list(route_elements.staticRoutes.route),
            )
        )

        return any(expect_description in desc for desc in route_descriptions)

    def add_static_route_on_bridge_edge_gateway(
        self,
        org_name: str,
        vdc_name: str,
        vdc_edge_gateway_name: str,
        public_network_cidr: str,
    ) -> None:
        """ Add a static route between public network and internal vdc network on
        bridge edge gateway

        :param org_name:
        :param vdc_name:
        :param vdc_edge_gateway_name:
        :param public_network_cidr:
        :return:
        """
        vdc_edge_gateway = self.__get_gateway(org_name, vdc_name, vdc_edge_gateway_name)

        assigned_ip = vdc_edge_gateway.list_external_network_ip_allocations().get(
            "VCD-EDGES"
        )[0]

        bridge_edge_gateway = self.__get_gateway("vdo", "vdo", "BRIDGE-EDGE")

        logger.info(
            f"Adding a static route in {vdc_edge_gateway_name}"
            f" (network: {public_network_cidr}, next hop: {assigned_ip}"
        )

        bridge_edge_gateway.add_static_route(
            public_network_cidr,
            assigned_ip,
            description=f"Created by {org_name}/{vdc_name}/{vdc_edge_gateway_name}",
        )

    def delete_static_routes_on_bridge_edge_gateway(
        self, org_name: str, vdc_name: str
    ) -> None:
        """Delete all static routes created for the vdc on bridge edge gateway

        :param org_name: associated org name
        :param vdc_name: associated vdc name
        :return:
        """
        bridge_edge_gateway = self.__get_gateway("vdo", "vdo", "BRIDGE-EDGE")

        static_routes_resource = bridge_edge_gateway.get_static_routes()
        static_routes_created_for_vdc = list(
            filter(
                lambda x: f"{org_name}/{vdc_name}" in str(x.description),
                static_routes_resource.staticRoutes.getchildren(),
            )
        )

        logger.debug(
            f"The number of static routes created for "
            f"{org_name}/{vdc_name}: {len(static_routes_created_for_vdc)}"
        )

        for static_route_resource in static_routes_created_for_vdc:
            public_network_cidr = static_route_resource.network

            static_route = StaticRoute(
                self.__client,
                gateway_name="BRIDGE-EDGE",
                route_network_id=public_network_cidr,
                route_resource=static_routes_resource,
            )

            # This is a hack! Need to set resource_id and href
            static_route._build_network_href()
            static_route._build_self_href("hmm.hack!")
            static_route.resource_id = public_network_cidr

            logger.info(
                f"Deleting static route <{static_route_resource.description}> "
                f"(network: {public_network_cidr}, nextHop: "
                f"{static_route_resource.nextHop}) from BRIDGE-EDGE"
            )

            static_route.delete_static_route()

    def edit_firewall_rule(
        self,
        org_name: str,
        vdc_name: str,
        edge_gateway_name: str,
        public_ip_address_cidr: str,
    ) -> None:
        """ Add a firewall rule to allow all incoming/outgoing requests
        go through this edge gateway.

        :param org_name: the org that edge gateway belongs to
        :param vdc_name: the vdc that edge gateway belongs to
        :param edge_gateway_name: target edge gateway name
        :param public_ip_address_cidr: public ip cidr range
        :return: None
        """
        rule_set: List[Dict[str, Any]] = [
            {
                "name": "inbound-rpcv-rule",
                "destination_values": [f"{public_ip_address_cidr}:ip"],
                "services": [
                    {"tcp": {"any": "22"}},
                    {"tcp": {"any": "443"}},
                    {"tcp": {"any": "8443"}},
                    {"tcp": {"any": "902"}},
                    {"tcp": {"any": "903"}},
                    {"udp": {"any": "902"}},
                ],
            },
            {
                "name": "outbound-rpcv-rule",
                "source_values": [f"{public_ip_address_cidr}:ip"],
            },
        ]

        edge_gateway: Gateway = self.__get_gateway(
            org_name, vdc_name, edge_gateway_name
        )

        logger.info(
            "Updating firewall rules in edge gateway", gateway=edge_gateway_name
        )

        for rule in rule_set:
            if self.__rule_exists(rule["name"], edge_gateway):
                logger.info(
                    "Firewall rule exists. Not need to update it", rule=rule["name"]
                )
            else:
                logger.info("Creating a new firewall rule", rule=rule["name"])
                self.__update_firewall(
                    edge_gateway_name,
                    edge_gateway,
                    rule["name"],
                    rule.get("source_values"),
                    rule.get("destination_values"),
                    rule.get("services"),
                )

    def update_usage_meter_guest_properties(
        self,
        org_name: str,
        vdc_name: str,
        usage_meter_vapp_name: str,
        vm_name: str,
        usage_meter_ip: str,
        gateway_ip: str,
        netmask: str,
        root_password: str,
        usgmtr_password: str,
    ) -> str:
        org = Org(
            client=self.__client, resource=self.__client.get_org_by_name(org_name)
        )
        vdc = VDC(client=self.__client, resource=org.get_vdc(vdc_name))

        vapp = VApp(client=self.__client, resource=vdc.get_vapp(usage_meter_vapp_name))

        vm = VmExtended(client=self.__client, resource=vapp.get_vm(vm_name))

        vm_product_sections_xml = vm.client.get_linked_resource(
            vm.resource, RelationType.DOWN, EntityType.PRODUCT_SECTIONS.value
        )

        vm.update_product_section_property(
            vm_product_sections_xml,
            key="gateway",
            class_name="vami",
            instance_name="vCloud_Usage_Meter",
            value=gateway_ip,
            user_configurable=True,
        )
        vm.update_product_section_property(
            vm_product_sections_xml,
            key="DNS",
            class_name="vami",
            instance_name="vCloud_Usage_Meter",
            value="8.8.8.8,8.8.4.4",
            user_configurable=True,
        )
        vm.update_product_section_property(
            vm_product_sections_xml,
            key="ip0",
            class_name="vami",
            instance_name="vCloud_Usage_Meter",
            value=usage_meter_ip,
            user_configurable=True,
        )
        vm.update_product_section_property(
            vm_product_sections_xml,
            key="netmask0",
            class_name="vami",
            instance_name="vCloud_Usage_Meter",
            value=netmask,
            user_configurable=True,
        )
        vm.update_product_section_property(
            vm_product_sections_xml,
            key="password",
            value=root_password,
            user_configurable=True,
        )
        vm.update_product_section_property(
            vm_product_sections_xml,
            key="usgmtr_password",
            value=usgmtr_password,
            user_configurable=True,
        )

        task = vm.send_updated_product_section(vm_product_sections_xml)
        task_href = task.get("href")

        logger.debug(
            "Submitted request to update the Usage Meter VM guest properties",
            vcenter=usage_meter_vapp_name,
            vm=vm_name,
            task_href=task_href,
        )
        return str(task_href)

    def __rule_exists(self, rule_name: str, edge_gateway: Gateway) -> bool:
        rules: List[Dict[str, Any]] = edge_gateway.get_firewall_rules_list()

        return any(str(r["name"]) == rule_name for r in rules)

    def __update_firewall(
        self,
        edge_gateway_name: str,
        edge_gateway: Gateway,
        rule_name: str,
        source_values: Optional[List[str]] = None,
        destination_values: Optional[List[str]] = None,
        services: Optional[List[Any]] = None,
    ) -> None:
        edge_gateway.add_firewall_rule(
            rule_name, action="accept", type="User", enabled=True
        )

        rules = edge_gateway.get_firewall_rules_list()

        rule = next(r for r in rules if r["name"] == rule_name)

        firewall_rule = FirewallRule(
            client=self.__client,
            gateway_name=edge_gateway_name,
            resource_id=rule["ID"],
        )

        firewall_rule.edit(
            source_values=source_values,
            destination_values=destination_values,
            services=services,
        )

    def __get_org(self, org_name: str) -> Org:
        org = Org(self.__client, resource=self.__client.get_org_by_name(org_name))

        return org

    def __get_vdc(self, org_name: str, vdc_name: str) -> VDC:
        org = self.__get_org(org_name)
        vdc = VDC(self.__client, resource=org.get_vdc(name=vdc_name))

        return vdc

    def __get_vapp(self, org_name: str, vdc_name: str, vapp_name: str) -> VApp:
        vdc = self.__get_vdc(org_name, vdc_name)

        vapp = VApp(self.__client, resource=vdc.get_vapp(vapp_name))

        return vapp

    def __get_gateway(self, org_name: str, vdc_name: str, gateway_name: str) -> Gateway:
        vdc = self.__get_vdc(org_name, vdc_name)

        # there are certain issues by passing resource=vdc.get_gateway(gateway_name)
        gateway = Gateway(self.__client, href=vdc.get_gateway(gateway_name).get("href"))

        return gateway
