from flask_rebar import RequestSchema
from marshmallow import fields


class NetworkCopySchema(RequestSchema):
    toHost = fields.String()
