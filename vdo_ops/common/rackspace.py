from itertools import chain
from typing import List, Optional, Iterator
from uuid import UUID

from common import constants, log
from common.clients.cms import Data as CmsData, CustomerAccount

logger = log.get_logger(__name__)

__BUSINESS_UNIT_KEY = "Business_Unit"
__RBU = "RBU"


def get_cloud_account(domain_id: str) -> CustomerAccount:
    return constants.CLIENTS.cms_client.get_customer_account(
        CmsData.TYPE_CLOUD, domain_id
    )


def create_org(domain_id: str, org_id: UUID, org_name: str) -> None:
    cloud_domain_account = constants.CLIENTS.cms_client.get_customer_account(
        CmsData.TYPE_CLOUD, domain_id
    )

    existing_org = constants.CLIENTS.cms_client.get_customer_account(
        CmsData.TYPE_RPCV, str(org_id)
    )

    if existing_org is not None:
        logger.info("Rackspace org has already been created in CMS", org=org_id)
    else:
        logger.info("Creating Rackspace org in cms", org=org_id)

        business_unit = cloud_domain_account.metadata.get(
            f"{CmsData.METADATA_CREATION_NAMESPACE}:{__BUSINESS_UNIT_KEY}", None
        )

        if business_unit is not None and business_unit.upper() == __RBU:
            metadata = {__BUSINESS_UNIT_KEY: business_unit}
        else:
            metadata = {}

        constants.CLIENTS.cms_client.add_customer_account_to_customer(
            cloud_domain_account.rcn,
            str(org_id),
            org_name,
            domain_id,
            CmsData.TYPE_RPCV,
            metadata,
        )


def close_org(org_id: UUID) -> None:
    logger.info("Closing Racksapce org in CMS", org=org_id)

    customer_account = constants.CLIENTS.cms_client.get_customer_account(
        CmsData.TYPE_RPCV, str(org_id)
    )
    constants.CLIENTS.cms_client.update_customer_account(
        CmsData.TYPE_RPCV,
        str(org_id),
        name=customer_account.name,
        status=CmsData.STATUS_CLOSED,
        rcn=customer_account.rcn,
    )


def get_orgs(
    domain_id: Optional[str] = None, search: Optional[str] = None
) -> List[CustomerAccount]:
    def is_matched(customer_account: CustomerAccount, search_term: str) -> bool:
        fields = ["id", "name", "rcn", "domain"]

        return any(
            search_term.lower() in getattr(customer_account, f).lower() for f in fields
        )

    logger.info("Getting Rackspace orgs from CMS")

    accounts: Iterator[CustomerAccount] = chain.from_iterable(
        constants.CLIENTS.cms_client.get_customer_accounts(CmsData.TYPE_RPCV, domain_id)
    )

    if search is None:
        orgs = list(accounts)
    else:
        orgs = list(filter(lambda account: is_matched(account, search), accounts))

    return orgs
