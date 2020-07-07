import os
import datetime
from pynamodb.models import Model
from pynamodb.attributes import UnicodeAttribute, TTLAttribute
from pynamodb.constants import STREAM_OLD_IMAGE
from pynamodb.exceptions import DoesNotExist
from common.config import USE_USER_TOKENS_TABLE


VALID_TYPES = ["aws-account"]
TTL_TYPES = {"aws-account": datetime.timedelta(60)}


def _get_table_prefix():
    stage = os.environ.get("STAGE")
    if stage != "prod":
        if not USE_USER_TOKENS_TABLE:
            return "dev"
    return stage


class TokenModel(Model):
    """
    A Token for token style authentication

    Properties:
        token_id: a UNIQUE composite key of `resource_type:resource_id`
        token: business specific token (like an org token or password)
    """

    class Meta:
        table_name = f"{_get_table_prefix()}-goss-api-tokens.v1"
        region = "us-west-2"
        stream_view_type = STREAM_OLD_IMAGE

    token_id = UnicodeAttribute(hash_key=True)
    token = UnicodeAttribute()
    ttl = TTLAttribute(null=True)


class Token(object):
    def _make_key(self, resource_id, resource_type):
        """
        Creates a combined key from the Arguments to be used as the token key

        Arguments:
            resource_id (string): A unique resource identifier, usually an org
                id, a username, etc.
            resource_type (string): The type of resource_id, must be from `VALID_TYPES`

        Returns:
            string: The combined token of resource_type:resource_id
        """
        return f"{resource_type}:{resource_id}"

    def create(self, token, resource_id, resource_type):
        """
        Create a token and store it in ddb

        Arguments:
            resource_id (string): unique identifier for a resource
            resource_type (string): The resource's type. Must be in VALID_TYPES

        Returns:
            string: The token content

        Raises:
            ValueError: Type specified does not match one of the valid types
            AttributeError: Token already exists for a resource id/type
        """
        if resource_type not in VALID_TYPES:
            msg = f"resource_type must be one of {VALID_TYPES}"
            raise ValueError(msg)
        existing_token = self.read(resource_id, resource_type)
        if existing_token is not None:
            raise AttributeError(f"Token Exists for {resource_type}:{resource_id}")
        ttl = None
        if resource_type in TTL_TYPES.keys():
            ttl = TTL_TYPES[resource_type]
        new_token = TokenModel(
            token_id=self._make_key(resource_id, resource_type), token=token, ttl=ttl
        )
        new_token.save()
        return new_token.token

    def read(self, resource_id, resource_type):
        """
        Find a token based on the scope you need. Only supports one token per
        id/type, so we are assuming we can pull the first.

        Arguments:
            resource_id (string): unique identifier for a resource
            resource_type (string): The resource's type. Must be in VALID_TYPES

        Returns:
            None: When no token can be found
            string: The token content
        """
        try:
            token = TokenModel.get(self._make_key(resource_id, resource_type))
        except DoesNotExist:
            return None
        return token.token

    def update(self, resource_id, resource_type, token):
        """
        Update the token contents. Only the token value itself is changeable.

        Arguments:
            resource_id (string): unique identifier for a resource
            resource_type (string): The resource's type. Must be in VALID_TYPES
            token (string): The new token value to change

        Returns:
            string: The token value

        Raises:
            ValueError: When asked to update a token that does not exist
        """
        token_id = self._make_key(resource_id, resource_type)
        try:
            found_token = TokenModel.get(token_id)
        except DoesNotExist:
            raise ValueError(f"Token not found: {token_id}")

        actions = [TokenModel.token.set(token)]
        resource_type, resource_id = found_token.token_id.split(":")
        if resource_type in TTL_TYPES:
            ttl = TTL_TYPES[resource_type]
            actions.append(TokenModel.ttl.set(ttl))
        found_token.update(actions=actions)
        return found_token.token

    def delete(self, resource_id, resource_type):
        """
        Purge the token in question.

        Arguments:
            resource_id (string): unique identifier for a resource
            resource_type (string): The resource's type. Must be in VALID_TYPES

        Returns:
            None: No takesies backsies
        """
        token_id = self._make_key(resource_id, resource_type)
        try:
            found_token = TokenModel.get(token_id)
            found_token.delete()
        except DoesNotExist:
            pass
        return None
