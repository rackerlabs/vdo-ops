"""
https://pages.github.rackspace.com/IX/internal-docs-customer-admin/api-docs/concepts
/index.html
"""
from dataclasses import dataclass
from typing import Optional, Iterator, List, cast, Dict, Any
from urllib import parse

from dacite import from_dict

from common import log
from common.clients.identity import IdentityAccount, IdentitySession

logger = log.get_logger(__name__)


class Data:
    TYPE_RPCV: str = "RPC_V"
    TYPE_CLOUD: str = "CLOUD"
    STATUS_ACTIVE: str = "Active"
    STATUS_CLOSED: str = "Closed"
    METADATA_CREATION_NAMESPACE: str = "creation"


@dataclass
class CustomerAccount:
    id: str
    name: str
    type: str
    status: str
    rcn: str
    createdBy: str
    createdDate: str
    domain: str
    serviceLevel: Optional[str]
    metadata: Optional[Dict[str, Any]]


class Cms:
    def __init__(self, endpoint: str, identity_account: IdentityAccount):
        self.__endpoint = endpoint
        self.__identity_account = identity_account

    def get_customer_account(self, type: str, id: str) -> Optional[CustomerAccount]:
        """
        https://pages.github.rackspace.com/IX/internal-docs-customer-admin/api-docs
        /api-reference/ops-customer-accounts.html#get-customer-account

        :param type:
        :param id:
        :return:
        """
        with IdentitySession(self.__identity_account) as session:
            response = session.get(
                f"{self.__endpoint}/v3/customer_accounts/{type}/{id}/detail"
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()

            data = response.json()

            return cast(
                CustomerAccount, from_dict(data_class=CustomerAccount, data=data)
            )

    def update_customer_account(
        self, type: str, id: str, name: str, status: str, rcn: str
    ) -> None:
        """
        https://pages.github.rackspace.com/IX/internal-docs-customer-admin/api-docs
        /api-reference/ops-customer-accounts.html#update-customer-account

        :param customer_account:
        :return:
        """
        with IdentitySession(self.__identity_account) as session:
            data = {"id": id, "name": name, "type": type, "status": status, "rcn": rcn}

            response = session.put(
                f"{self.__endpoint}/v3/customer_accounts/{type}/{id}", json=data
            )

            response.raise_for_status()

    def create_or_update_customer_account_metadata(
        self, type: str, id: str, metadata_key: str, metadata_value: str
    ) -> None:
        """
        https://pages.github.rackspace.com/IX/internal-docs-customer-admin/api-docs
        /api-reference/ops-customer-accounts.html#update-specific-metadata
        :param key:
        :param value:
        :return:
        """
        with IdentitySession(self.__identity_account) as session:
            data = {"meta": {metadata_key: metadata_value}}

            response = session.put(
                f"{self.__endpoint}/v3/customer_accounts/{type}/{id}/metadata/"
                f"{metadata_key}",
                json=data,
            )

            response.raise_for_status()

    def get_customer_accounts(
        self, type: str, domain: Optional[str] = None
    ) -> Iterator[List[CustomerAccount]]:
        """
        https://pages.github.rackspace.com/IX/internal-docs-customer-admin/api-docs
        /api-reference/ops-customer-accounts.html#get-customer-accounts

        :param type:
        :param domain:
        :return:
        """
        with IdentitySession(self.__identity_account) as session:
            next_id = None
            has_data = True

            while has_data:
                if next_id is None:
                    current_marker = None
                else:
                    current_marker = f"{type}:{next_id}"

                response = session.get(
                    f"{self.__endpoint}/v3/customer_accounts",
                    params={
                        "domain": domain,
                        "accountType": type,
                        "direction": "backward",
                        "marker": current_marker,
                    },
                )

                response.raise_for_status()

                data = response.json()

                accounts = list(
                    map(
                        lambda item: cast(
                            CustomerAccount,
                            from_dict(data_class=CustomerAccount, data=item),
                        ),
                        data["customerAccount"],
                    )
                )

                yield accounts

                next_link = next(
                    (link for link in data["link"] if link["rel"] == "NEXT"), None
                )

                if next_link is not None:
                    next_marker = parse.parse_qs(
                        parse.urlsplit(next_link["href"]).query
                    )["marker"]
                    next_id = next_marker[0].split(":")[-1]
                else:
                    next_id = None
                    has_data = False

    def add_customer_account_to_customer(
        self,
        rcn: str,
        id: str,
        name: str,
        domain: str,
        type: str,
        metadata: Dict[str, Any],
        status: str = Data.STATUS_ACTIVE,
    ) -> None:
        """
        https://pages.github.rackspace.com/IX/internal-docs-customer-admin/api-docs
        /api-reference/ops-customers.html#add-customer-account

        CMS will add "creation" namespace prefix to all keys during creation
        :param rcn:
        :param id:
        :param name:
        :param domain:
        :param type:
        :param metadata:
        :param status:
        :return:
        """
        with IdentitySession(self.__identity_account) as session:
            data = {
                "id": id,
                "name": name,
                "rcn": rcn,
                "domain": domain,
                "type": type,
                "status": status,
                "metadata": metadata,
            }

            response = session.post(
                f"{self.__endpoint}/v3/customers/{rcn}/customer_accounts", json=data
            )

            response.raise_for_status()
