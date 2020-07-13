import os
from uuid import uuid4

import boto3

public_ips = [
    "83.138.177.32/28",
    "83.138.177.48/28",
    "134.213.47.128/28",
    "134.213.47.144/28",
    "212.100.235.96/28",
    "212.100.235.112/28",
]

stage = os.environ.get("STAGE")
aws_profile_name = os.environ.get("AWS_PROFILE")
aws_region = os.environ.get("AWS_DEFAULT_REGION")
profile_name = os.environ.get("PROFILE_NAME")


def validate_env(env_name: str, not_allowed: list = None) -> str:
    val = os.environ.get(env_name)

    if val is None:
        raise Exception(f"env {env_name} does not exist")

    print(f"{env_name}: {val}")

    if not_allowed is not None and val.lower() in map(lambda x: x.lower(), not_allowed):
        raise Exception(f"{val} is not allowed for env {env_name}")

    return val


def local_pre_deploy_check():
    validate_env("STAGE", ["dev", "prod"])
    validate_env("AWS_PROFILE")
    validate_env("AWS_DEFAULT_REGION")
    validate_env("PROFILE_NAME")


def generate_seeds():
    table_name = f"{stage}-rpcvdb-1"

    print(f"table: {table_name}")
    print()

    # We get a lot for free from environment variables
    session = boto3.Session(
        profile_name=aws_profile_name, region_name=aws_region
    )

    table = session.resource('dynamodb').Table(table_name)

    print("Generating public ip blocks...")

    with table.batch_writer() as batch:
        for public_ip in public_ips:
            batch.put_item(
                Item={
                    "domain": "PUBLIC_NETWORK",
                    "type_uuid": f"public_net_{str(uuid4())}",
                    "assigned": False,
                    "public_ip_block": public_ip,
                }
            )

    print("Generating dummy data...")

    data = [
        # this org has been already registered in CMS.
        # It is highly recommended to re-use it
        {
            "domain": "1280717",
            "type_uuid": "org_c398934c-1064-4df5-846b-611fd9256e7c",
            "name": "vdo-rpcv-test-org",
            "vcd_region": "lab",
            "rcn": "RCN-100-000-303-992",
            "status": "ACTIVE",
            "created_date": "2020-04-21T00:49:05.303265+0000",
            "index_alpha_pk": "org",
            "index_alpha_sk": "c398934c-1064-4df5-846b-611fd9256e7c",
            "index_beta_pk": "name",
            "index_beta_sk": "vdo-rpcv-test-org_c398934c-1064-4df5-846b-611fd9256e7c",
        },
        # same fake data
        {
            "domain": "1280717",
            "type_uuid": "org_07ee133c-0175-4d64-b0f6-33729b7d6c78",
            "name": "dummy-test-org",
            "vcd_region": "lab",
            "rcn": "RCN-000-000-000-000",
            "status": "ACTIVE",
            "created_date": "2020-04-21T00:49:05.303265+0000",
            "index_alpha_pk": "org",
            "index_alpha_sk": "07ee133c-0175-4d64-b0f6-33729b7d6c78",
            "index_beta_pk": "name",
            "index_beta_sk": "dummy-test-org_07ee133c-0175-4d64-b0f6-33729b7d6c78",
        },
        {
            "domain": "1280717",
            "type_uuid": "cluster_6fe17045-66ee-4a54-9e9b-ada1186baff0",
            "vdc_name": "dummy-test-cluster",
            "org_id": "07ee133c-0175-4d64-b0f6-33729b7d6c78",
            "public_network_id": "x",
            "public_network_block": "x",
            "vdc_number": 2,
            "vcenter_ip": "1.1.1.1",
            "vcenter_dns": "vcenter.sddc-99.1280717.dev.rpc-v.rackspace-cloud.com",
            "status": "ACTIVE",
            "index_beta_pk": "cluster",
            "index_beta_sk": "6fe17045-66ee-4a54-9e9b-ada1186baff0",
        },
        {
            "domain": "1280717",
            "type_uuid": "host_42b3820e-49df-42d7-8b2f-d9688415016c",
            "ip": "127.0.0.1",
            "org_id": "07ee133c-0175-4d64-b0f6-33729b7d6c78",
            "cluster_id": "6fe17045-66ee-4a54-9e9b-ada1186baff0",
            "status": "ACTIVE",
        }
    ]

    with table.batch_writer() as batch:
        for item in data:
            batch.put_item(Item=item)
