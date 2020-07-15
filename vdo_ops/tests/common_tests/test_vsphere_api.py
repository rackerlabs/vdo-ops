import mock
import pytest
from mock import Mock, patch
from unittest.mock import call
from common import secrets

VCENTER_HOST = "123.123.123.123"


class TestSessionManager:
    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture(autouse=True)
def monkeypatch_ssm(monkeypatch):
    def mock_return(path):
        return "SECRET"

    monkeypatch.setattr(secrets, "get_parameter", mock_return)


def test_vcenter_init(get_handler):
    handler = get_handler("common.vsphere_api")

    with mock.patch.object(handler, "VsphereClient") as vsphere_client:
        handler.VsphereApi(VCENTER_HOST)
        vsphere_client.assert_called_with(VCENTER_HOST)


@patch("common.vsphere_api.VsphereClient")
def test_copy_networks(client_mock, get_handler):
    vsphere_api_handler = get_handler("common.vsphere_api")

    client_mock.open_session.return_value = TestSessionManager()

    # setup
    spec = Mock()
    from_switch1 = Mock()
    from_switch1.name = "from1"
    from_switch2 = Mock()
    from_switch2.name = "from2"
    from_switch2.spec = spec
    client_mock.get_host_virtual_switches.return_value = [from_switch1, from_switch2]
    client_mock.has_virtual_switch.side_effect = [True, False]

    client_mock.add_host_vswitch.return_value = Mock()

    portgroup = Mock()
    portgroup_spec = Mock()
    portgroup_spec.name = "p1"
    portgroup.spec = portgroup_spec
    portgroup1 = Mock()
    portgroup_spec1 = Mock()
    portgroup_spec1.name = "p2"
    portgroup1.spec = portgroup_spec1
    client_mock.get_portgroup_by_vswitch.return_value = [portgroup, portgroup1]
    client_mock.is_in_do_not_copy_list.side_effect = [True, False, True, False]
    client_mock.has_portgroup.side_effect = [False, False]

    client_mock.add_host_portgroup.return_value = Mock()

    vsphere_api = vsphere_api_handler.VsphereApi(VCENTER_HOST)
    vsphere_api._client = client_mock

    # when
    vsphere_api.copy_networks("from", "to")

    # then
    client_mock.open_session.assert_called()

    client_mock.get_host_virtual_switches.assert_called_with("from")
    calls = [
        call("to", "from1"),
        call("to", "from2"),
    ]
    client_mock.has_virtual_switch.assert_has_calls(calls, any_order=True)
    client_mock.add_host_vswitch.assert_called_with("to", "from2", spec)
    client_mock.add_host_portgroup.assert_called_with("to", portgroup_spec1)
