import flask_rebar

from common import log
from flask_rebar import errors
from schemas.error import ErrorResponseSchema
from schemas.header import GlobalHeadersSchema
from schemas.host import NetworkCopySchema
from schemas.common import GenericSuccessResponseSchema
from server.rebar import registry
import boto3
import json
from common import constants

lambda_client = boto3.client("lambda")

logger = log.get_logger(__name__)

BASE_URL = "/host/<int:device_id>"


@registry.handles(
    rule=f"{BASE_URL}/network_copy",
    method="POST",
    headers_schema=GlobalHeadersSchema(),
    request_body_schema=NetworkCopySchema(),
    response_body_schema={
        202: GenericSuccessResponseSchema(),
        500: ErrorResponseSchema,
    },
)
def network_copy(device_id):
    body = flask_rebar.get_validated_body()

    to_host_device = body["toHost"]

    payload = {"from_host_id": device_id, "to_host_device": to_host_device}

    function_name = f"{constants.STAGE}-vdo-ops-network_copy"
    response = lambda_client.invoke(
        FunctionName=function_name, Payload=json.dumps(payload)
    )
    if "FunctionError" in response:
        raise errors.InternalError(response["FunctionError"])
    return {"success": "successfully copied network settings"}, 202
