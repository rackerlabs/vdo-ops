import os
from typing import Any, Dict

from common import constants
from common.clients import boto


def get_path(category: str = "") -> str:
    stage: str = constants.STAGE
    if category == "":
        category = "config"
    return os.environ.get("SSM_PARAMS_PATH", f"/rpcv/{stage}/{category}")


def get_secrets_from_ssm(category: str = "") -> Dict[str, Any]:
    ssm_client = boto.get_client(boto.ClientType.SIMPLE_SYSTEMS_MANAGER)
    secrets: Dict[str, Any] = {}
    path = get_path(category)
    params = ssm_client.get_parameters_by_path(
        Path=f"{path}/", Recursive=True, WithDecryption=True
    )["Parameters"]
    for param in params:
        name = param["Name"].replace(f"{path}/", "")
        secrets[name] = param["Value"]
    return secrets


def get_parameter(path):
    ssm_client = boto.get_client(boto.ClientType.SIMPLE_SYSTEMS_MANAGER)
    result = ssm_client.get_parameter(Name=path, WithDecryption=True)
    return result["Parameter"]["Value"]
