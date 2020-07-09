import json
from dataclasses import asdict, dataclass
from typing import Any

from botocore.exceptions import ClientError
from dacite import from_dict

from common import constants
from common.clients import boto
from common.clients.boto import ClientType
from common.log import logger


@dataclass
class VcenterSecret:
    root_username: str
    root_password: str
    admin_username: str
    admin_password: str


@dataclass
class UsageMeterSecret:
    root_username: str
    root_password: str
    usgmtr_username: str
    usgmtr_password: str


@dataclass
class ZamboniSecret:
    username: str
    password: str


@dataclass
class ServiceAccountSecret:
    username: str
    password: str


@dataclass
class HostSecret:
    username: str
    password: str


class SecretManager:
    def __init__(self) -> None:
        self.__stage = constants.STAGE
        self.__system_manager = boto.get_client(ClientType.SIMPLE_SYSTEMS_MANAGER)
        self.__secrets_manager = boto.get_client(ClientType.SECRETS_MANAGER)

    def get_vcenter_info_key(self, org_id: str, cluster_id: str, dns_name: str) -> str:
        modified_dns_name = dns_name.rstrip(".")
        return (
            f"/rpcv/{self.__stage}/orgs/{org_id}/clusters/{cluster_id}/vcenters/"
            f"{modified_dns_name}"
        )

    def get_usage_meter_info_key(
        self, org_id: str, cluster_id: str, dns_name: str
    ) -> str:
        modified_dns_name = dns_name.rstrip(".")

        # lint was complaining return line was too long so I split it up annoyingly
        base = f"/rpcv/{self.__stage}"
        return (
            f"{base}/orgs/{org_id}/clusters/{cluster_id}/usage_meters/"
            f"{modified_dns_name}"
        )

    def get_zamboni_info_key(self, org_id: str, cluster_id: str, dns_name: str) -> str:
        modified_dns_name = dns_name.rstrip(".")

        # lint was complaining return line was too long so I split it up annoyingly
        base = f"/rpcv/{self.__stage}"
        return (
            f"{base}/orgs/{org_id}/clusters/{cluster_id}/vcenters/"
            f"{modified_dns_name}/readonly"
        )

    def get_host_info_key(self, org_id: str, cluster_id: str, ip: str) -> str:
        return f"/rpcv/{self.__stage}/orgs/{org_id}/clusters/{cluster_id}/hosts/{ip}"

    def __persist_data(self, key: str, secret_string: str) -> None:
        try:
            self.__secrets_manager.create_secret(
                Name=key, SecretString=secret_string,
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceExistsException":
                logger.exception("Secret already exists. Try to update the value.")

                self.__secrets_manager.update_secret(
                    SecretId=key, SecretString=secret_string,
                )
            else:
                raise e

    def is_vcenter_in_secret_manager(self, vcenter_dns: str) -> bool:
        modified_vcenter_dns_name = vcenter_dns.rstrip(".")

        secrets_resp = self.__secrets_manager.list_secrets()
        secrets_list = secrets_resp["SecretList"]

        while "NextToken" in secrets_resp:
            secrets_resp = self.__secrets_manager.list_secrets(
                NextToken=secrets_resp["NextToken"]
            )
            secrets_list.extend(secrets_resp["SecretList"])

        num_of_vcenter_secrets = len(
            [
                secret
                for secret in secrets_list
                if (modified_vcenter_dns_name in secret["Name"])
                and (secret["Name"].startswith(f"/rpcv/{self.__stage}"))
            ]
        )

        if num_of_vcenter_secrets == 0:
            logger.debug(f"Vcenter DNS: {vcenter_dns} not found in the secrets manager")
            return False
        else:
            logger.debug(f"Vcenter DNS: {vcenter_dns} found in the secrets manager")
            return True

    def persist_secret(self, key: str, secret: Any) -> None:
        """
        Save secret into secrets manager

        :param key:
        :return:
        """
        secret_string = json.dumps(asdict(secret))

        logger.info(f"Persisting {key} secret...")

        self.__persist_data(key, secret_string)

    def secret_info_exists(self, key: str) -> bool:
        """
        Check if secret already exists

        :param key:
        :return:
        """
        try:
            self.__secrets_manager.get_secret_value(SecretId=key)["SecretString"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                logger.exception(f"Secret {key} info is not found")
                return False
            else:
                raise e
        return True

    def get_secret_info(self, key: str, secret_class: Any) -> Any:
        """
        Get Usage Meter Secrets info
        :param key:
        :param secret_class:
        :return:
        """
        secret_string = self.__secrets_manager.get_secret_value(SecretId=key)[
            "SecretString"
        ]

        return from_dict(data_class=secret_class, data=json.loads(secret_string))
