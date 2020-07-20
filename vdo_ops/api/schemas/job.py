from flask_rebar import ResponseSchema
from marshmallow import fields

from common import constants


class JobResponseSchema(ResponseSchema):
    job_id = fields.UUID(attribute="type_uuid")
    status = fields.Integer()
    step_number = fields.Integer()
    total_steps = fields.Integer()
    result_ref = fields.Url(required=False, allow_none=True, missing=None)
    error = fields.String(required=False, allow_none=True)
    job_ref = fields.Function(lambda job: f"{constants.URLBASE}/jobs/{job.type_uuid}")
