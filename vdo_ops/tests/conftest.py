from importlib import import_module

import pytest


@pytest.fixture
def get_handler():
    def _handler(name):
        handler = import_module(name)
        return handler

    return _handler
