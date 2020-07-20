from dataclasses import dataclass
from typing import List, Any
from flask_rebar import ResponseSchema
from marshmallow import fields


@dataclass
class ApiResponseDataSet:
    count: int
    items: List[Any]

    @staticmethod
    def from_items(items: List[Any]) -> "ApiResponseDataSet":
        return ApiResponseDataSet(count=len(items), items=items)


class GenericSuccessResponseSchema(ResponseSchema):
    success = fields.String(required=False, allow_none=True)
