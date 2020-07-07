import jwt
import json
import arrow
from common import requests, log
from common.constants import (
    AZURE_OATH_URL,
    AZURE_MANAGEMENT_URL,
    MSCLOUD_OATH_URL,
    MSCLOUD_API_URL,
)

logger = log.setup_logging()
requests = requests.requests


class MSCloudClient(object):
    def __init__(self, client_id, client_secret):
        self.access_token = None
        self.token_expiration = None
        self.client_id = client_id
        self.client_secret = client_secret

    def get_token_expiration(self):
        """
        Get the number of seconds left in a token.
        """

        return self.token_expiration - arrow.utcnow().timestamp

    def get_access_token(self):
        """
        Fetch an access token for the master org.

        This also stores the access token in the object so it can be
        re-used on multiple requests.
        """

        if self.access_token:
            exp = self.get_token_expiration()
            # Only used the cached token if it is valid for more than
            # one minute.
            if exp >= 60:
                return self.access_token

        auth_body = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "clientapp",
        }
        resp = requests.post(f"{MSCLOUD_OATH_URL}/connect/token", data=auth_body)
        resp.raise_for_status()
        self.access_token = resp.json()["access_token"]
        self.token_expiration = arrow.utcnow().timestamp + 3600
        return self.access_token

    def get_subscription(self, subscription_id):
        headers = {
            "Authorization": f"Bearer {self.get_access_token()}",
        }

        url = f"{MSCLOUD_API_URL}/subscription/{subscription_id}"
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


class AzureRestClient(object):
    def __init__(self, tenant_id, client_id, client_secret):
        self.access_token = None
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.resource = "https://management.azure.com/"
        self.client_secret = client_secret

    def get_token_expiration(self):
        """
        Get the number of seconds left in a token.
        """

        exp = jwt.decode(self.access_token, verify=False)["exp"]
        return exp - arrow.utcnow().timestamp

    def get_access_token(self):
        """
        Fetch an access token for the master org.

        This also stores the access token in the object so it can be
        re-used on multiple requests.
        """

        if self.access_token:
            exp = self.get_token_expiration()
            # Only used the cached token if it is valid for more than
            # one minute.
            if exp >= 60:
                return self.access_token

        auth_body = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "resource": self.resource,
        }
        resp = requests.post(
            f"{AZURE_OATH_URL}/{self.tenant_id}/oauth2/token", data=auth_body
        )
        resp.raise_for_status()
        self.access_token = resp.json()["access_token"]
        return self.access_token

    def run_command(self, vm_location, command):
        script_body = {"commandId": "RunShellScript", "script": [command]}
        headers = {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Content-Type": "application/json",
        }

        url = f"{AZURE_MANAGEMENT_URL}{vm_location}/runCommand?api-version=2019-03-01"
        logger.info("Running command.", url=url)
        resp = requests.post(url, headers=headers, data=json.dumps(script_body))
        resp.raise_for_status()
        return resp.headers["Azure-AsyncOperation"]

    def get_async_result(self, async_url):
        headers = {
            "Authorization": f"Bearer {self.get_access_token()}",
        }

        url = f"{async_url}"
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()
