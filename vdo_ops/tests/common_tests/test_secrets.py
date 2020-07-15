import mock


def test_get_path_no_category(get_handler):
    secrets = get_handler("common.secrets")
    secrets.constants.STAGE = "dev"
    my_path = secrets.get_path()
    assert my_path == "/rpcv/dev/config"


def test_get_path_with_category(get_handler):
    secrets = get_handler("common.secrets")
    secrets.constants.STAGE = "dev"
    my_path = secrets.get_path("foobar")
    assert my_path == "/rpcv/dev/foobar"


def test_get_secrets_from_ssm(get_handler):
    secrets = get_handler("common.secrets")

    class FakeSSM:
        def get_parameters_by_path(*args, **kwargs):
            fake_params = {
                "Parameters": [
                    {"Name": "/foobar/foo", "Value": "bar"},
                    {"Name": "/foobar/bin", "Value": "baz"},
                ]
            }
            return fake_params

    fake_return = {"foo": "bar", "bin": "baz"}
    with mock.patch.object(
        secrets, "get_path", mock.Mock(return_value="/foobar")
    ), mock.patch.object(secrets.boto, "get_client", mock.Mock(return_value=FakeSSM)):
        assert secrets.get_secrets_from_ssm() == fake_return


def test_get_parameter(get_handler):
    secrets = get_handler("common.secrets")

    class FakeSSM:
        def get_parameter(*args, **kwargs):
            fake_param = {"Parameter": {"Name": "/foobar/foo", "Value": "bar"}}
            return fake_param

    fake_return = "bar"
    with mock.patch.object(secrets.boto, "get_client", mock.Mock(return_value=FakeSSM)):
        assert secrets.get_parameter("path") == fake_return
