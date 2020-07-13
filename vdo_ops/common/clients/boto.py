import os
from enum import unique, Enum
from typing import Any, Dict

import boto3
import botocore

from common import constants, log

REGION = os.environ.get("REGION", "us-west-2")


@unique
class ClientType(Enum):
    STEP_FUNCTIONS = "stepfunctions"
    SECURITY_TOKEN_SERVICE = "sts"
    SIMPLE_SYSTEMS_MANAGER = "ssm"
    ROUTE53 = "route53"
    SECRETS_MANAGER = "secretsmanager"
    BATCH = "batch"
    DDB = "dynamodb"


@unique
class Route53Actions(Enum):
    CREATE = "CREATE"
    DELETE = "DELETE"
    UPSERT = "UPSERT"


@unique
class Route53RecordTypes(Enum):
    A = "A"
    CNAME = "CNAME"


@unique
class StepfunctionStatus(Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    ABORTED = "ABORTED"


class TaskFailureException(Exception):
    pass


logger = log.get_logger(__name__)


def get_boto_session() -> boto3.Session:
    env_kwargs = {
        "aws_access_key_id": os.environ.get("AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY"),
        "aws_session_token": os.environ.get("AWS_SESSION_TOKEN"),
        "region_name": REGION,
    }

    for k, v in env_kwargs.copy().items():
        if v is None:
            env_kwargs.pop(k)

    return boto3.Session(**env_kwargs)


def get_client(client_type: ClientType) -> botocore.client:
    session = get_boto_session()
    return session.client(client_type.value)


def make_arn(resource_type: str, resource_descriptor: str) -> str:
    sts = get_client(ClientType.SECURITY_TOKEN_SERVICE)
    account_id = sts.get_caller_identity()["Account"]
    return f"arn:aws:{resource_type}:{REGION}:{account_id}:{resource_descriptor}"


def get_state_machine_definition(executionArn: str) -> Any:
    sfn = get_client(ClientType.STEP_FUNCTIONS)
    execution = sfn.describe_execution(executionArn=executionArn)
    state_machine_arn = execution["stateMachineArn"]
    return sfn.describe_state_machine(stateMachineArn=state_machine_arn)["definition"]


def make_host_name(host_name: str, domain: str) -> str:
    domain_suffix = constants.CUSTOMER_DNS_DOMAIN_NAME
    return ".".join([host_name, domain, domain_suffix])


def manage_dns_record(
    record: str,
    ip: str,
    action: Route53Actions = Route53Actions.UPSERT,
    record_type: Route53RecordTypes = Route53RecordTypes.A,
    ttl: int = 60,
) -> None:
    r53 = get_client(ClientType.ROUTE53)
    request = {
        "HostedZoneId": constants.CUSTOMER_DNS_ZONE_ID,
        "ChangeBatch": {
            "Changes": [
                {
                    "Action": action.value,
                    "ResourceRecordSet": {
                        "Name": record,
                        "Type": record_type.value,
                        "TTL": ttl,
                        "ResourceRecords": [{"Value": ip}],
                    },
                }
            ]
        },
    }
    r53.change_resource_record_sets(**request)


def initiate_batch_job(
    job_name: str, job_queue: str, job_def: str, params: Dict[str, str]
) -> str:
    batch_client = get_client(ClientType.BATCH)

    queues = batch_client.describe_job_queues()
    job_queue_name = next(
        filter(lambda queue: job_queue in queue["jobQueueName"], queues["jobQueues"])
    )["jobQueueName"]

    j_definitions = batch_client.describe_job_definitions()
    deploy_job_def_name = next(
        filter(
            lambda j_def: job_def in j_def["jobDefinitionName"],
            j_definitions["jobDefinitions"],
        )
    )["jobDefinitionName"]

    job_response = batch_client.submit_job(
        jobName=job_name,
        jobQueue=job_queue_name,
        jobDefinition=deploy_job_def_name,
        parameters=params,
    )

    return str(job_response["jobId"])


def check_batch_job_status(batch_job_id: str) -> bool:
    batch_client = get_client(ClientType.BATCH)
    job_status_response = batch_client.describe_jobs(jobs=[batch_job_id])

    status = job_status_response["jobs"][0]["status"]

    if "SUCCEEDED" in status.upper():
        return True
    elif "FAILED" in status.upper():
        raise TaskFailureException(f"status={status}")
    else:
        logger.debug(f"Job: {batch_job_id} is in status: {status}")
        return False


def get_state_machine_status(execution_arn: str) -> str:
    sfn = get_client(ClientType.STEP_FUNCTIONS)
    execution = sfn.describe_execution(executionArn=execution_arn)
    return str(execution["status"])
