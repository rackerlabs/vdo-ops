import os
from typing import Any, Dict

from common import constants
from common.clients import boto
from common.clients.boto import ClientType


def get_path(category: str = "") -> str:
    stage: str = constants.STAGE
    if category == "":
        category = "config"
    return os.environ.get("SSM_PARAMS_PATH", f"/rpcv/{stage}/{category}")


def get_secrets_from_ssm(category: str = "") -> Dict[str, Any]:
    secrets: Dict[str, Any] = {}
    path = get_path(category)
    ssm_client = boto.get_client(ClientType.SIMPLE_SYSTEMS_MANAGER)
    params = ssm_client.get_parameters_by_path(
        Path=f"{path}/", Recursive=True, WithDecryption=True
    )["Parameters"]
    for param in params:
        name = param["Name"].replace(f"{path}/", "")
        secrets[name] = param["Value"]
    return secrets
