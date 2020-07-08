import json

from pyVim import connect
from pyVmomi import vim

from common import requests
from common import log
from common.constants import (
    ZAMBONI_URL,
    WATCHMAN_API_PROD_URL,
)
from common.exceptions import VCenterError

requests = requests.requests
logger = log.setup_logging()


class VcenterClient(object):
    def __init__(self, vc_hostname, cloud_username, cloud_password):
        self.vc_hostname = vc_hostname
        self.cloud_username = cloud_username
        self.cloud_password = cloud_password
        self._service_index = None
        logger.info("Connected to vCenter: " + vc_hostname)

    @property
    def service_index(self):
        if self._service_index is None:
            service_index = connect.SmartConnectNoSSL(
                host=self.vc_hostname,
                user=self.cloud_username,
                pwd=self.cloud_password,
                port=443,
            )
            self._service_index = service_index
        return self._service_index

    def get_roleId_by_name(self, name):
        return next(
            (
                role.roleId
                for role in self.service_index.content.authorizationManager.roleList
                if role.name == name
            ),
            None,
        )

    def assign_principal_to_role(self, principal, roleId, isGroup=True):
        auth_manager = self.service_index.content.authorizationManager
        e = self.service_index.content.rootFolder
        perm = vim.AuthorizationManager.Permission(
            entity=e, group=isGroup, principal=principal, propagate=True, roleId=roleId
        )
        auth_manager.SetEntityPermissions(e, [perm])

    def get_vm_by_uuid(self, vm_uuid):
        """ Fetch vm from vcenter by uuid.

        Arguments:
            vm_uuid (UUIDv4): UUID of the vm in question

        Returns:
            vm (pyVmomi.vim.VirtualMachine): A pyVim managed object of
                the virtual machine
        """
        logger.info("Fetching vm: " + vm_uuid)
        search_index = self.service_index.content.searchIndex

        datacenter = None
        vm_search = True
        instance_uuid = True
        vm = search_index.FindByUuid(datacenter, vm_uuid, vm_search, instance_uuid)
        logger.info("Found VM: " + vm.name)
        return vm

    def set_custom_attribute(self, vm_uuid, tag_name, tag_value):
        """ Assigns tag to a VM. Must search for tags in the registry first
        and will create the necessary tag first if not found.

        Removing tags from virtual machines is not implemented in vCenter. While
        the rationale behind such an obvious missing feature is inscrutible and
        maddening, we are left with the unfortunate denouement of adopting the
        convention of setting the tag_value to an empty string ('') to signify
        that a tag has been deleted.

        Arguments:
            vm_uuid (UUIDv4): UUID of the vm in question
            tag_name (string): usually ssmid or some other key
            tag_value (string): usually mi-<whatever> or some other value

        Returns:
            None
        """
        custom_fields_manager = self.service_index.content.customFieldsManager
        vm = self.get_vm_by_uuid(vm_uuid)
        if vm is None:
            raise VCenterError(f"No VM with ID {vm_uuid} was found.")
        names = [f.name for f in custom_fields_manager.field]
        if tag_name not in names:
            custom_fields_manager.AddCustomFieldDef(
                name=tag_name, moType=vim.VirtualMachine
            )
        vm.setCustomValue(key=tag_name, value=tag_value)


class VcenterRESTClient(object):
    def __init__(self, vc_hostname, cloud_username, cloud_password):
        self.vc_hostname = vc_hostname
        self.cloud_username = cloud_username
        self.cloud_password = cloud_password
        self._session_id = None

    @property
    def session_id(self):
        if self._session_id is None:
            sess = requests.post(
                f"https://{self.vc_hostname}/rest/com/vmware/cis/session",
                auth=(self.cloud_username, self.cloud_password),
            )
            session_id = sess.json()["value"]
            self._session_id = session_id
        return self._session_id

    def add_ad_group(self, group):
        """ Add a group to the local SSO group

        Arguments:
            group (String): Name of the group to add

        Returns:
            None
        """
        r = requests.post(
            f"https://{self.vc_hostname}/rest/hvc/management/administrators?action=add",
            data=json.dumps({"group_name": group}),
            headers={
                "vmware-api-session-id": self.session_id,
                "Content-type": "application/json",
            },
        )
        r.raise_for_status()


class ZamboniClient(object):
    def __init__(self, identity_client):
        self.identity_client = identity_client

        self.zamboni_url = ZAMBONI_URL

        self.fields = [
            "id",  # This fixes a pagination bug in Zamboni
            "location",
            "body.name",
            "body._rackspace",
            "body.availableField",
            "body.value",
            "body.config.instanceUuid",
            "body.config.uuid",
            "body.guest",
        ]

    def get_vm_by_id(self, id):
        headers = {
            "Accept": "application/json",
            "X-Auth-Token": self.identity_client.token,
        }
        params = {
            "filters[body.config.instanceUuid]": id,
            "filters[service]": "vsphere",
            "fields": ",".join(self.fields),
        }
        url = f"{self.zamboni_url}/instances/"

        r = requests.get(url, headers=headers, params=params)
        r.raise_for_status()

        data = r.json()["data"]

        if len(data) == 1:
            return data[0]
        elif len(data) > 1:
            raise Exception(f"More than one VM with ID {id} found")
        else:
            return None

    def get_vm_by_urn(self, urn):
        headers = {
            "Accept": "application/json",
            "X-Auth-Token": self.identity_client.token,
        }
        params = {"filters[urn]": urn}
        url = f"{self.zamboni_url}/instances/"

        r = requests.get(url, headers=headers, params=params)
        r.raise_for_status()

        data = r.json()["data"]

        if len(data) == 1:
            return data[0]
        elif len(data) > 1:
            raise Exception(f"More than one VM with URN {urn} found")
        else:
            return None

    def get_vms_by_vcenter(self, vcenter):
        headers = {
            "Accept": "application/json",
            "X-Auth-Token": self.identity_client.token,
        }
        params = {
            "filters[location]": vcenter,
            "filters[body._rackspace.isManagementVM]": "false",
            "filters[service]": "vsphere",
            "sort": "name",
            "fields": ",".join(self.fields),
        }
        url = f"{self.zamboni_url}/instances/"

        r = requests.get(url, headers=headers, params=params)
        r.raise_for_status()
        return r.json()["data"]


class WatchmanClient(object):
    def __init__(self, identity_client):
        self.identity_client = identity_client

        self.base_url = WATCHMAN_API_PROD_URL

    def get_webhooks(self, domain, account):
        headers = {"X-Auth-Token": self.identity_client.token, "X-Tenant-Id": domain}
        url = f"{self.base_url}/v1/{account}/webhooks"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        return r.json()["webhooks"]

    def get_webhook(self, domain, account, rel):
        for webhook in self.get_webhooks(domain, account):
            if webhook["rel"] == rel:
                return webhook

        return None

    def post_message(self, domain, account, rel, payload):
        webhook = self.get_webhook(domain, f"faws:{account}", rel)

        if not webhook:
            raise Exception(f"no webhook with name {rel} found for domain {domain}")

        path = webhook["href"]
        r = requests.post(
            url=f"{self.base_url}{path}",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
        )
        r.raise_for_status()
