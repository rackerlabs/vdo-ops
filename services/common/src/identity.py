import os

import arrow
from fleece import log

from common import requests

logger = log.get_logger()
requests = requests.requests


class RackspaceIdentity(object):
    def __init__(self, username, password, domain=None):
        self.url = _get_base_url_for_stage()
        self.username = username
        self.password = password
        self.domain = domain
        self._token = None
        self.expires_at = 0
        self.expiration_padding = 3600

    def authenticate(self):
        body = {
            "auth": {
                "passwordCredentials": {
                    "username": self.username,
                    "password": self.password,
                }
            }
        }

        if self.domain:
            body["auth"]["RAX-AUTH:domain"] = {"name": self.domain}

        resp = requests.post(f"{self.url}/v2.0/tokens", json=body)

        if not resp.ok:
            logger.error(f"Identity authentication failed - {resp.status_code}")
            resp.raise_for_status()

        auth = resp.json()["access"]["token"]

        self._token = auth["id"]
        self.expires_at = arrow.get(auth["expires"]).timestamp - self.expiration_padding

        logger.info("Refreshed Identity Token...")
        return self.token

    @property
    def is_expired(self):
        return arrow.utcnow().timestamp >= self.expires_at

    @property
    def token(self):
        if self._token and not self.is_expired:
            return self._token
        return self.authenticate()


def _get_base_url_for_stage():
    stage = os.environ.get("STAGE", "local")
    if stage == "local":
        return "https://identity-internal.api.rackspacecloud.com"
    else:
        return "https://proxy.api.manage.rackspace.com/identity"


def validate(token):
    url = _get_base_url_for_stage()
    resp = requests.get(f"{url}/v2.0/tokens/{token}", headers={"x-auth-token": token})
    resp.raise_for_status()
    return resp.json()
