import os
from typing import NamedTuple

from fleece import log

from common import requests
from common.constants import (
    ENCORE_API_URL,
    ENCORE_API_PROXY_URL,
    ENCORE_SUPPORT_API_URL,
)

logger = log.get_logger()
requests = requests.requests


class Comment(NamedTuple):
    text: str
    is_public: bool

    def to_dict(self):
        return {"text": self.text, "is_public": self.is_public}


class Ticket(NamedTuple):
    subject: str
    description: str
    category_id: str
    sub_category_id: str
    group: str
    comment: Comment = None
    tags: list = []

    def to_dict(self):
        body = {
            "subject": self.subject,
            "description": self.description,
            "category_id": self.category_id,
            "sub_category_id": self.sub_category_id,
            "group": self.group,
            "tags": self.tags,
        }
        body["comment"] = self.comment.to_dict() if self.comment else None
        return body


class EncoreClient(object):
    def __init__(self, token):
        self.url = _get_base_url_for_stage()
        self.support_url = ENCORE_SUPPORT_API_URL
        self.token = token

    def create_ticket(self, tenant, ticket):
        """https://github.rackspace.com/lefty/ticket_service/wiki/Ticket-API#create-ticket"""
        resp = requests.post(
            f"{self.url}/v1/accounts/{tenant}/tickets",
            json=ticket.to_dict(),
            headers={"x-auth-token": self.token},
        )
        resp.raise_for_status()

        body = resp.json()
        return body["ticket"]["ticket_id"]

    def update_ticket(self, tenant, ticket_id, comment):
        resp = requests.put(
            f"{self.url}/v1/accounts/{tenant}/tickets/{ticket_id}",
            json={"comment": comment.to_dict()},
            headers={"x-auth-token": self.token},
        )
        resp.raise_for_status()


def _get_base_url_for_stage():
    stage = os.environ.get("STAGE", "local")
    if stage == "local":
        return ENCORE_API_URL
    else:
        return ENCORE_API_PROXY_URL
