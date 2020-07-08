import os

import boto3
from fleece import log

logger = log.get_logger()

# Token Service: (Set True to use your user's token db instead of `dev`)
USE_USER_TOKENS_TABLE = False


def get_ssm_client(**kwargs):
    return boto3.client("ssm", **kwargs)


def get_path():
    # assure trailing slash is present in path
    return os.path.join(os.environ.get("SSM_PARAMS_PATH", "/vdo/global"), "")


def get_secrets_from_ssm():
    secrets = {}
    path = get_path()
    if not path:
        logger.warning(
            "No SSM_PARAMS_PATH path set! Continuing without SSM configuration."
        )
        return secrets
    ssm_client = get_ssm_client()
    params = ssm_client.get_parameters_by_path(
        Path=path, Recursive=True, WithDecryption=True
    )["Parameters"]
    for param in params:
        name = param["Name"].replace(path, "")
        secrets[name] = param["Value"]
    return secrets
