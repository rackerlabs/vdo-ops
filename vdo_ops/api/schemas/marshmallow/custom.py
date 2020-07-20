from marshmallow import fields


class CustomList(fields.List):
    """
    Allow marshmallow to return [] if the value of the list is None

    Team(name="vdo", alias=None, members: List = None, projects = ["rpcv", "goss"])
    -> { "name": vdo, "alias": null, members: [], "project": ["rpcv", "goss] }
    """

    def __init__(self, cls_or_instance, **kwargs):  # type: ignore
        super().__init__(cls_or_instance, **kwargs)

    def get_value(self, attr, obj, accessor=None):  # type: ignore
        value = super().get_value(attr, obj, accessor)

        if value is None:
            return fields.missing_
        else:
            return value


class EnrichedQueryString(fields.String):
    """
    Allow marshmallow to treat an empty string as a missing field

    """

    def _deserialize(self, value, attr, data):  # type: ignore
        if value == "":
            return fields.missing_

        return super()._deserialize(value, attr, data)


class ToUppercaseString(fields.String):
    """
    Allow marshmallow to serialize a string to its uppercase
    """

    def _serialize(self, value, attr, obj):  # type: ignore
        return super()._serialize(value.upper(), attr, obj)


class EnrichedDnsString(fields.String):
    """
    Allow marshmallow to serialize a dns name to the one without trailing dot (.)
    """

    def _serialize(self, value, attr, obj):  # type: ignore
        enriched_value = value.rstrip(".")
        return super()._serialize(enriched_value, attr, obj)


class DnsToUrlString(fields.String):
    """
    Allow marshmallow to serialize a dns name to a url
    """

    def _serialize(self, value, attr, obj):  # type: ignore
        if value is not None:
            enriched_value = value.rstrip(".")
            return super()._serialize(f"https://{enriched_value}", attr, obj)
        else:
            return fields.missing_
