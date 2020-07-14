from flask_rebar import ResponseSchema
from marshmallow import fields, Schema


class ErrorSchema(Schema):
    id = fields.String()
    message = fields.String()
    data = fields.Dict(required=False)


class ErrorResponseSchema(ResponseSchema):
    error = fields.Nested(ErrorSchema)
