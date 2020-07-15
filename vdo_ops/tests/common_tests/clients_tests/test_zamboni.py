import pytest
from mock import patch, Mock

from tests.helper import util

TARGET_MODULE = "common.clients.zamboni"


@pytest.fixture
def zamboni_fixture(get_handler):
    zamboni = get_handler(TARGET_MODULE)

    with patch(f"{TARGET_MODULE}.IdentitySession") as identity_session_module_mock:
        session_mock = Mock()
        identity_session_module_mock.return_value.__enter__.return_value = session_mock

        yield [zamboni.Zamboni("test-endpoint", Mock()), session_mock]


def test_get_vms_by_vcenter(zamboni_fixture):
    zamboni_subject, session_mock = zamboni_fixture

    # setup
    data = util.load_json_file("data/zamboni/get_vm_list.json")

    response_mock = util.to_mock({"json()": data})
    session_mock.get.return_value = response_mock

    # when
    actual = zamboni_subject.get_vms_by_vcenter("vcenter")

    # then
    session_mock.get.assert_called_with(
        "test-endpoint/rpcv/vsphere/virtual_machines",
        params={
            "filters[location]": "vcenter",
            "fields": "id,name,location,provider_account_id,body.name,"
            "body._rackspace,body._metadata,"
            "body.availableField,body.value,body.config.instanceUuid,"
            "body.config.uuid,body.guest",
        },
    )
    response_mock.raise_for_status.assert_called()
    response_mock.json.assert_called()

    assert len(actual) == 5
    assert actual[0]["name"] == "Hounsou-Test-2012-Std"


def test_get_vms_by_vcenter_returns_none(zamboni_fixture):
    zamboni_subject, session_mock = zamboni_fixture

    # setup
    response_mock = Mock(status_code=404)
    session_mock.get.return_value = response_mock

    # when
    actual = zamboni_subject.get_vms_by_vcenter("vcenter")

    # then
    session_mock.get.assert_called_with(
        "test-endpoint/rpcv/vsphere/virtual_machines",
        params={
            "filters[location]": "vcenter",
            "fields": "id,name,location,provider_account_id,"
            "body.name,body._rackspace,body._metadata,"
            "body.availableField,body.value,body.config.instanceUuid,"
            "body.config.uuid,body.guest",
        },
    )
    response_mock.raise_for_status.assert_not_called()
    response_mock.json.assert_not_called()

    assert actual is None


def test_get_hyps_by_device_id(zamboni_fixture):
    zamboni_subject, session_mock = zamboni_fixture

    # setup
    data = util.load_json_file("data/zamboni/get_host_system.json")

    response_mock = util.to_mock({"json()": data})
    session_mock.get.return_value = response_mock

    # when
    actual = zamboni_subject.get_hyps_by_device_id("364027")

    # then
    session_mock.get.assert_called_with(
        "test-endpoint/managedvirt/vsphere/host_systems",
        params={
            "filters[body._rackspace.deviceId]": "364027",
            "fields": "id,location,resource_id,body.name,body._rackspace",
        },
    )
    response_mock.raise_for_status.assert_called()
    response_mock.json.assert_called()

    assert len(actual) == 5
    assert actual["name"] == "364027-hyp90.ord1.rvi.local"
