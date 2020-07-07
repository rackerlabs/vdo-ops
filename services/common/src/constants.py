import os
from enum import Enum

# In an effort to reduce redundancies, this file should contain common,
# hard-coded values used throughout the project.

STAGE = os.environ.get("STAGE", "dev")

# Goss monitoring values
GOSS_MON_USER_NAME = "vdo_monitoring_user"
GOSS_MON_POLICY_NAME = "monitoring_user_policy"
GOSS_MON_USER_PATH = "/rackspace/monitoring/"

# Janus
JANUS_API_BASE_URL = "https://accounts.api.manage.rackspace.com"
JANUS_TTL = 900

# Zamboni
if STAGE == "dev":
    ZAMBONI_URL = "https://staging.resources.rackspace.net"
else:
    ZAMBONI_URL = "https://resources.rackspace.net"

# Encore
ENCORE_API_URL = "https://api.ticketing.encore.rackspace.com"
ENCORE_API_PROXY_URL = "https://proxy.api.manage.rackspace.com/encore-api"
ENCORE_SUPPORT_API_URL = "https://support.encore.rackspace.com"
ENCORE_VMC_GROUP_NAME = "Private Cloud-VMware-VMC"
ENCORE_GTS_LINUX_GROUP = "Global Linux OS Anywhere"
ENCORE_GTS_WINDOWS_GROUP = "Global Windows - VMC on AWS"
ENCORE_VMWARE_MANAGED_SERVICES_GROUP_NAME = "VMware Advanced Managed Services"

# Watchman
WATCHMAN_API_PROD_URL = "https://watchman.api.manage.rackspace.com"

# Azure
AZURE_MANAGEMENT_URL = "https://management.azure.com"
AZURE_OATH_URL = "https://login.microsoftonline.com"
MSCLOUD_OATH_URL = "https://auth.mscloud.rackspace.com"
MSCLOUD_API_URL = "https://api.mscloud.rackspace.com/api/v1"


class GOSSServices(Enum):
    OS_ADMIN = "com.rackspace.goss.vm.services.os.admin"
    PATCHING = "com.rackspace.goss.vm.services.patching"
    MONITORING = "com.rackspace.goss.vm.services.monitoring"
