import json
from typing import Any, Dict, List, Tuple

import requests
from fleece.authpolicy import AuthPolicy
from requests.structures import CaseInsensitiveDict

from common import log

logger = log.get_logger(__name__)

TOKEN_URL_FMT = "https://heimdall.api.manage.rackspace.com/v2.0/tokens/{token}"


def validate(token: str) -> Any:
    """Validate token and return auth context."""
    token_url = TOKEN_URL_FMT.format(token=token)
    headers = {
        "x-auth-token": token,
        "accept": "application/json",
    }
    resp = requests.get(token_url, headers=headers)

    if not resp.status_code == 200:
        logger.error("Unauthorized request", response_code=resp.status_code)
        raise Exception("Unauthorized")
    return resp.json()


def parse_method_arn(method_arn: str) -> Tuple[List[str], str, str]:
    parts = method_arn.split(":")
    api_gateway_arn = parts[5].split("/")
    aws_account_id = parts[4]
    region = parts[3]
    return api_gateway_arn, aws_account_id, region


def is_racker(identity_response: Dict[str, Any]) -> bool:
    """Examine roles and return True if Racker role present."""
    roles = identity_response.get("access", {}).get("user", {}).get("roles", [])
    for role in roles:
        if role.get("name") == "Racker" and role.get("id") == "9":
            return True
    return False


def filter_role(role: Dict[str, str]) -> Dict[str, str]:
    """ Remove unwanted keys to save space. """
    unwanted = ["description"]
    filtered: Dict[str, str] = {}
    for k in role.keys():
        if k not in unwanted:
            filtered[k] = role[k]
    return filtered


def handler(event: Dict[str, Any], context: Any) -> Any:
    method_arn = event["methodArn"]
    api_gateway_arn, aws_account_id, region = parse_method_arn(method_arn)
    headers: CaseInsensitiveDict[str] = CaseInsensitiveDict(event.get("headers", {}))
    proposed_token = headers.get("x-auth-token", "")
    identity = validate(proposed_token)
    roles = list(filter(filter_role, identity["access"]["user"]["roles"]))

    policy = AuthPolicy(
        aws_account_id,
        rest_api_id=api_gateway_arn[0],
        region=region,
        stage=api_gateway_arn[1],
    )

    racker = is_racker(identity)
    if racker is True:
        domain_id = headers.get("x-tenant-id", None)
    else:
        domain_id = identity["access"]["user"].get("RAX-AUTH:domainId", None)

    if domain_id:
        policy.allow_all_methods()

        response = policy.build()
        response["context"] = {
            "domainId": domain_id,
            "name": identity["access"]["user"]["name"],
            "userId": identity["access"]["user"]["id"],
            "racker": racker,
            "roles": json.dumps(roles),
        }
    else:
        policy.deny_all_methods()

        response = policy.build()
        response["context"][
            "errorMessage"
        ] = "Domain Id not found in both Identity and request headers"

    logger.info(f"Policy: {response}")
    return response
