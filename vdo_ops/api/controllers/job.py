from typing import Tuple
from uuid import UUID

import flask_rebar
from flask_rebar import errors
from pynamodb.exceptions import DoesNotExist

from common import log
from common.ddb.v0 import JobModel
from schemas.error import ErrorResponseSchema
from schemas.header import GlobalHeadersSchema
from schemas.job import JobResponseSchema
from server.rebar import registry

logger = log.get_logger(__name__)


@registry.handles(
    rule="/jobs/<uuid:job_id>",
    method="GET",
    headers_schema=GlobalHeadersSchema(),
    response_body_schema={200: JobResponseSchema(), 404: ErrorResponseSchema()},
)
def get_job(job_id: UUID) -> Tuple[JobModel, int]:
    domain = flask_rebar.get_validated_headers()["domain"]

    try:
        job = JobModel.get(domain, str(job_id))
    except DoesNotExist:
        raise errors.NotFound(f"Job {job_id} not found.")

    return job, 200
