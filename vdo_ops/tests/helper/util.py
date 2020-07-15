import json
import os
from typing import Dict

from mock import Mock


def load_json_file(path: str) -> Dict:
    with open(os.path.join(os.path.dirname(__file__), f"../{path}")) as f:
        return json.load(f)


def to_mock(behaviors: Dict):
    """
    util.mock({"json()": something}) is the same as
    Mock(**{"json.return_value": something})

    :param behaviors:
    :return:
    """

    def transform_key(key: str):
        return key.replace("()", ".return_value")

    transformed_behaviors = {transform_key(k): v for k, v in behaviors.items()}

    return Mock(**transformed_behaviors)
