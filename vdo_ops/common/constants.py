import os
from enum import Enum, unique
from functools import cached_property
from typing import List

from common.clients.cms import Cms
from common.clients.zamboni import Zamboni
from common.clients.vdo_goss import VdoGoss
from common import secrets
from common.clients.identity import IdentityAccount

STAGE = os.environ.get("STAGE", "dev")
REGION = os.environ.get("REGION", "us-west-2")
SNAT = "snat"
DNAT = "dnat"
os.environ.setdefault("APP_LOCATION", "local")

DEPLOY_APPLIANCE_JOB_DEFINITION_NAME = "deploy-appliance-batch-job-definition"
JOB_QUEUE_NAME = "batch-processing-job-queue"

if os.environ.get("APP_LOCATION") == "local":
    CMS_ENDPOINT = "https://customer-admin.api.rackspace.net"
    ZAMBONI_URL = "https://staging.resources.rackspace.net"
else:
    CMS_ENDPOINT = "https://proxy.api.manage.rackspace.com/customer-admin"
    ZAMBONI_URL = "https://staging.resources.rackspace.net"

ZAMBONI_IDENTITY_USER = "rpcv_dev"
CMS_IDENTITY_USER = "vmc_dev"
VDO_IDENTITY_USER = "vdo_dev"

if STAGE == "prod":
    CUSTOMER_DNS_ZONE_ID = "Z3BO5I3FWIZJL2"
    CUSTOMER_DNS_DOMAIN_NAME = "rpc-v.rackspace-cloud.com."
    URLBASE = "https://api.rpc-v.rackspace-cloud.com/api"
    VDO_URL = "https://api.goss.vdo.manage.rackspace.com/v1.0"
else:
    CUSTOMER_DNS_ZONE_ID = "Z1WJRHPTHRD7KU"
    CUSTOMER_DNS_DOMAIN_NAME = "dev.rpc-v.rackspace-cloud.com."
    if STAGE == "dev":
        URLBASE = "https://api.dev.rpc-v.rackspace-cloud.com/api"
    else:
        URLBASE = f"https://{STAGE}-api.dev.rpc-v.rackspace-cloud.com/api"
    VDO_URL = "https://api.goss.dev.vdo.manage.rackspace.com/v1.0"


class Platform(Enum):
    VCLOUD = "vcloud"
    OTHER = "other"

    @staticmethod
    def list_values() -> List[str]:
        return [platform.value for platform in Platform]


class JobStatus(Enum):
    PROCESSING = 1
    COMPLETE = 2
    ERROR = 3


@unique
class LifecycleStatus(Enum):
    PENDING_CREATION = "PENDING_CREATION"
    ACTIVE = "ACTIVE"

    PENDING_DELETION = "PENDING_DELETION"
    DISABLED = "DISABLED"


class IdentityUsers:
    if os.environ.get("APP_LOCATION") == "local":
        IDENTITY_ENDPOINT = "https://identity-internal.api.rackspacecloud.com"
    else:
        IDENTITY_ENDPOINT = "https://proxy.api.manage.rackspace.com/identity"

    @cached_property
    def vmc_dev(self) -> IdentityAccount:
        return IdentityUsers.get_account(
            IdentityUsers.IDENTITY_ENDPOINT, "identity/vmc_dev"
        )

    @cached_property
    def rpcv_dev(self) -> IdentityAccount:
        return IdentityUsers.get_account(
            IdentityUsers.IDENTITY_ENDPOINT, "identity/rpcv_dev"
        )

    @cached_property
    def vdo_dev(self) -> IdentityAccount:
        return IdentityUsers.get_account(
            IdentityUsers.IDENTITY_ENDPOINT, "identity/vdo_dev"
        )

    @staticmethod
    def get_account(endpoint: str, ssm_path: str) -> IdentityAccount:
        data = secrets.get_secrets_from_ssm(ssm_path)
        return IdentityAccount(endpoint, data["username"], data["password"])


IDENTITY_USERS = IdentityUsers()


class Clients:
    @cached_property
    def cms_client(self) -> Cms:
        return Cms(CMS_ENDPOINT, getattr(IDENTITY_USERS, CMS_IDENTITY_USER))

    @cached_property
    def zamboni_client(self) -> Zamboni:
        return Zamboni(ZAMBONI_URL, getattr(IDENTITY_USERS, ZAMBONI_IDENTITY_USER))

    @cached_property
    def vdo_goss_client(self) -> VdoGoss:
        return VdoGoss(VDO_URL, getattr(IDENTITY_USERS, VDO_IDENTITY_USER))


CLIENTS = Clients()


@unique
class ServiceType(Enum):
    NSX = "nsx"
    TURBONOMICS = "turbonomics"

    @staticmethod
    def list_values() -> List[str]:
        return [s.value for s in ServiceType]


class Licenses:
    @staticmethod
    def get_automation_licenses() -> List[str]:
        data = secrets.get_secrets_from_ssm("licenses")
        return [data[key] for key in data]
