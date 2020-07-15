import pytest
from botocore.exceptions import ClientError
from mock import patch, Mock, call

from common import constants  # noqa: F401
from common.clients import boto
from common.clients.boto import ClientType
from common.secret_manager import VcenterSecret

__STAGE = "test-stage"
__ORD_ID = "c64c6ded-d07d-4e1b-8963-d633163776b5"
__CLUSTER_ID = "7d233235-3b38-4c50-bd35-008dd13a6485"
__IP = "1.1.1.1"
__USERNAME = "test-username"
__PASSWORD = "test-password"
__SECRET_STR = '{"username": "test-username", "password": "test-password"}'
__VCENTER_SECRET = VcenterSecret("root", "root-password", "admin", "admin-password")
__VCENTER_SECRET_STR = (
    '{"root_username": "root", "root_password": "root-password", '
    '"admin_username": "admin", "admin_password": "admin-password"}'
)


def test_secret_manager_init(get_handler):
    handler = get_handler("common.secret_manager")

    with patch("common.constants.STAGE", __STAGE), patch.object(
        boto, "get_client"
    ) as get_client_mock:
        # setup
        system_manager_mock = Mock()
        secrets_manager_mock = Mock()

        def __get_boto_client(*args, **kwargs):
            if args[0] == ClientType.SIMPLE_SYSTEMS_MANAGER:
                return system_manager_mock
            else:
                return secrets_manager_mock

        get_client_mock.side_effect = __get_boto_client

        # when
        actual = handler.SecretManager()

        # then
        assert __get_protected_value(actual, "stage") == __STAGE
        assert __get_protected_value(actual, "system_manager") == system_manager_mock
        assert __get_protected_value(actual, "secrets_manager") == secrets_manager_mock


def __create_secret_manager_subject(get_handler):
    handler = get_handler("common.secret_manager")
    system_manager_mock = Mock()
    secrets_manager_mock = Mock()

    with patch("common.constants.STAGE", __STAGE), patch.object(
        boto, "get_client"
    ) as get_client_mock:

        def __get_boto_client(*args, **kwargs):
            if args[0] == ClientType.SIMPLE_SYSTEMS_MANAGER:
                return system_manager_mock
            else:
                return secrets_manager_mock

        get_client_mock.side_effect = __get_boto_client

        secret_manager = handler.SecretManager()

        return secret_manager, system_manager_mock, secrets_manager_mock, handler


def test_secret_manager_persist_vcenter_info_create_secret(get_handler):
    (
        secret_manager,
        system_manager_mock,
        secrets_manager_mock,
        handler,
    ) = __create_secret_manager_subject(get_handler)
    key = f"/rpcv/{__STAGE}/orgs/{__ORD_ID}/clusters/{__CLUSTER_ID}/vcenters/{__IP}"

    # when
    secret_manager.persist_secret(key, __VCENTER_SECRET)

    # then
    secrets_manager_mock.create_secret.assert_called_with(
        Name=f"/rpcv/{__STAGE}/orgs/{__ORD_ID}/clusters/{__CLUSTER_ID}/vcenters/{__IP}",
        SecretString=__VCENTER_SECRET_STR,
    )


def test_secret_manager_persist_vcenter_info_update_secret(get_handler):
    (
        secret_manager,
        system_manager_mock,
        secrets_manager_mock,
        handler,
    ) = __create_secret_manager_subject(get_handler)

    # setup
    secrets_manager_mock.create_secret.side_effect = ClientError(
        {"Error": {"Message": "bla", "Code": "ResourceExistsException"}}, "CreateSecret"
    )
    key = f"/rpcv/{__STAGE}/orgs/{__ORD_ID}/clusters/{__CLUSTER_ID}/vcenters/{__IP}"

    # when
    secret_manager.persist_secret(key, __VCENTER_SECRET)

    # then
    secrets_manager_mock.create_secret.assert_called_with(
        Name=key, SecretString=__VCENTER_SECRET_STR,
    )

    secrets_manager_mock.update_secret.assert_called_with(
        SecretId=key, SecretString=__VCENTER_SECRET_STR,
    )


def test_vcenter_info_exists_returns_True(get_handler):
    (
        secret_manager,
        system_manager_mock,
        secrets_manager_mock,
        handler,
    ) = __create_secret_manager_subject(get_handler)

    # setup
    secrets_manager_mock.get_secret_value.return_value = {
        "SecretString": f"{__VCENTER_SECRET_STR}"
    }
    key = f"/rpcv/{__STAGE}/orgs/{__ORD_ID}/clusters/{__CLUSTER_ID}/vcenters/{__IP}"

    # when
    actual = secret_manager.secret_info_exists(key)

    # then
    secrets_manager_mock.get_secret_value.assert_called_with(SecretId=key)

    assert actual is True


def test_vcenter_info_exists_returns_False(get_handler):
    (
        secret_manager,
        system_manager_mock,
        secrets_manager_mock,
        handler,
    ) = __create_secret_manager_subject(get_handler)

    # setup
    secrets_manager_mock.get_secret_value.side_effect = ClientError(
        {"Error": {"Message": "bla", "Code": "ResourceNotFoundException"}},
        "secretsmanager:GetSecretValue",
    )
    key = f"/rpcv/{__STAGE}/orgs/{__ORD_ID}/clusters/{__CLUSTER_ID}/vcenters/{__IP}"

    # when
    actual = secret_manager.secret_info_exists(key)

    # then
    secrets_manager_mock.get_secret_value.assert_called_with(SecretId=key)
    assert actual is False


def test_vcenter_info_exists_raise_exception(get_handler):
    (
        secret_manager,
        system_manager_mock,
        secrets_manager_mock,
        handler,
    ) = __create_secret_manager_subject(get_handler)

    # setup
    secrets_manager_mock.get_secret_value.side_effect = ClientError(
        {"Error": {"Message": "bla", "Code": "bla"}}, "secretsmanager:GetSecretValue"
    )
    key = f"/rpcv/{__STAGE}/orgs/{__ORD_ID}/clusters/{__CLUSTER_ID}/vcenters/{__IP}"

    # when
    with pytest.raises(
        ClientError, match="GetSecretValue operation: bla",
    ):
        secret_manager.secret_info_exists(key)

    # then
    secrets_manager_mock.get_secret_value.assert_called_with(SecretId=key)


def test_secret_manager_get_vcenter_info(get_handler):
    (
        secret_manager,
        system_manager_mock,
        secrets_manager_mock,
        handler,
    ) = __create_secret_manager_subject(get_handler)

    # setup
    secrets_manager_mock.get_secret_value.return_value = {
        "SecretString": f"{__VCENTER_SECRET_STR}"
    }
    key = f"/rpcv/{__STAGE}/orgs/{__ORD_ID}/clusters/{__CLUSTER_ID}/vcenters/{__IP}"

    # when
    actual = secret_manager.get_secret_info(key, VcenterSecret)

    # then
    secrets_manager_mock.get_secret_value.assert_called_with(SecretId=key)

    assert actual == __VCENTER_SECRET


def test_is_vcenter_in_secret_manager_return_true(get_handler):
    (
        secret_manager,
        system_manager_mock,
        secrets_manager_mock,
        handler,
    ) = __create_secret_manager_subject(get_handler)

    secrets_manager_mock.list_secrets.side_effect = [
        {
            "SecretList": [
                {"Name": f"/rpcv/{__STAGE}/orgs/o1/clusters/cluster1/vcenters/1.2.3.4"},
                {"Name": f"/rpcv/{__STAGE}/orgs/o1/clusters/cluster1/vcenters/1.2.3.5"},
            ],
            "NextToken": "next_1",
        },
        {
            "SecretList": [
                {"Name": f"/rpcv/{__STAGE}/orgs/o1/clusters/cluster1/vcenters/1.2.3.6"},
                {"Name": f"/rpcv/{__STAGE}/orgs/o1/clusters/cluster1/vcenters/1.2.3.7"},
            ],
            "NextToken": "next_2",
        },
        {
            "SecretList": [
                {"Name": f"/rpcv/{__STAGE}/orgs/o1/clusters/cluster1/vcenters/1.2.3.8"},
                {"Name": f"/rpcv/{__STAGE}/orgs/o1/clusters/cluster1/vcenters/1.2.3.9"},
            ],
        },
    ]

    result = secret_manager.is_vcenter_in_secret_manager("1.2.3.9")

    assert result is True

    secrets_manager_mock.list_secrets.assert_has_calls(
        [call(), call(NextToken="next_1"), call(NextToken="next_2")]
    )


def test_is_vcenter_in_secret_manager_return_false(get_handler):
    (
        secret_manager,
        system_manager_mock,
        secrets_manager_mock,
        handler,
    ) = __create_secret_manager_subject(get_handler)

    secrets_manager_mock.list_secrets.side_effect = [
        {
            "SecretList": [
                {"Name": f"/rpcv/{__STAGE}/orgs/o1/clusters/cluster1/vcenters/1.2.3.4"},
                {"Name": f"/rpcv/{__STAGE}/orgs/o1/clusters/cluster1/vcenters/1.2.3.5"},
            ],
            "NextToken": "next_1",
        },
        {
            "SecretList": [
                {"Name": f"/rpcv/{__STAGE}/orgs/o1/clusters/cluster1/vcenters/1.2.3.6"},
                {"Name": f"/rpcv/{__STAGE}/orgs/o1/clusters/cluster1/vcenters/1.2.3.7"},
            ],
            "NextToken": "next_2",
        },
        {
            "SecretList": [
                {"Name": f"/rpcv/{__STAGE}/orgs/o1/clusters/cluster1/vcenters/1.2.3.8"},
                {"Name": "/rpcv/dev/orgs/o1/clusters/cluster1/vcenters/1.2.3.9"},
            ],
        },
    ]

    result = secret_manager.is_vcenter_in_secret_manager("1.2.3.9")

    assert result is False

    secrets_manager_mock.list_secrets.assert_has_calls(
        [call(), call(NextToken="next_1"), call(NextToken="next_2")]
    )


def test_is_vcenter_in_secret_manager_return_true_less_values(get_handler):
    (
        secret_manager,
        system_manager_mock,
        secrets_manager_mock,
        handler,
    ) = __create_secret_manager_subject(get_handler)

    secrets_manager_mock.list_secrets.return_value = {
        "SecretList": [
            {"Name": f"/rpcv/{__STAGE}/orgs/o1/clusters/cluster1/vcenters/1.2.3.4"},
            {"Name": f"/rpcv/{__STAGE}/orgs/o1/clusters/cluster1/vcenters/1.2.3.5"},
        ],
    }

    result = secret_manager.is_vcenter_in_secret_manager("1.2.3.5")

    assert result is True

    secrets_manager_mock.list_secrets.assert_called_once()


def __get_protected_value(obj, name):
    class_name = type(obj).__name__

    return getattr(obj, f"_{class_name}__{name}")


def __set_protected_value(obj, name, value):
    class_name = type(obj).__name__

    return setattr(obj, f"_{class_name}__{name}", value)
