import arrow

from common import requests
from common.constants import JANUS_API_BASE_URL, JANUS_TTL


credentials_cache = {}
requests = requests.requests


class JanusClient(object):
    def __init__(self, token=None):
        self.token = token
        self.expiration_padding = 10

    def create_aws_account(self, name):
        path = f"{JANUS_API_BASE_URL}/v0/awsAccounts"
        resp = requests.post(
            path,
            headers={"x-auth-token": self.token},
            json={"awsAccount": {"name": name, "serviceLevelId": "aws.service_blocks"}},
        )
        resp.raise_for_status()
        return resp.json()

    def get_credentials(self, aws_account, domain):
        if self._is_cached(aws_account):
            return credentials_cache[aws_account]["credential"]

        return self._get_credentials(aws_account, domain)

    def _get_credentials(self, aws_account, domain):
        headers = {"X-Tenant-Id": domain, "X-Auth-Token": self.token}
        payload = {"credential": {"duration": JANUS_TTL}}
        path = f"{JANUS_API_BASE_URL}/v0/awsAccounts/{aws_account}/credentials"
        resp = requests.post(path, headers=headers, json=payload)

        resp.raise_for_status()
        credentials_cache[aws_account] = resp.json()
        credentials_cache[aws_account]["expires"] = self._get_expiration()
        return resp.json()["credential"]

    def _get_expiration(self):
        return (
            arrow.utcnow()
            .shift(seconds=(JANUS_TTL - self.expiration_padding))
            .timestamp
        )

    @staticmethod
    def _is_cached(aws_account):
        if credentials_cache.get(aws_account):
            expires = credentials_cache[aws_account]["expires"]
            if expires <= arrow.utcnow().timestamp:
                del credentials_cache[aws_account]
                return False
            else:
                return True
        else:
            return False
