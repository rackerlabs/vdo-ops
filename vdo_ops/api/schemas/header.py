from marshmallow import Schema, fields


class GlobalHeadersSchema(Schema):
    domain = fields.String(required=True, load_from="x-tenant-id")


class DomainNotRequiredHeadersSchema(Schema):
    domain = fields.String(required=False, load_from="x-tenant-id")
