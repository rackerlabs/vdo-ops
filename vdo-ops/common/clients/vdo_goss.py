"""
https://github.com/rackerlabs/vdo-goss
"""
from typing import Any, Dict, List

from common import log
from common.clients.identity import IdentityAccount, IdentitySession

logger = log.get_logger(__name__)


class VdoGoss:
    def __init__(self, endpoint: str, identity_account: IdentityAccount):
        self.__endpoint = endpoint
        self.__identity_account = identity_account

    def enroll_vm(
        self,
        tenant_id: str,
        vm_info: Dict[str, Any],
        vcenter_info: Dict[str, Any],
        aws_account: str,
        region: str,
        services: List[str],
    ) -> Dict[str, str]:
        request_params = {
            "service": "rpcv",
            "vm_username": vm_info["username"],
            "vm_password": vm_info["password"],
            "vm_uuid": vm_info["uuid"],
            "vcenter_username": vcenter_info["username"],
            "vcenter_password": vcenter_info["password"],
            "vcenter": vcenter_info["host"],
            "vcenter_port": vcenter_info["port"],
            "aws_account": aws_account,
            "region": region,
            "services": services,
        }
        headers = {
            "X-Tenant-Id": tenant_id,
        }

        with IdentitySession(self.__identity_account) as session:
            response = session.post(
                f"{self.__endpoint}/goss/enroll", headers=headers, json=request_params
            )

        response.raise_for_status()
        return {"job_status": response.headers.get("Location")}
