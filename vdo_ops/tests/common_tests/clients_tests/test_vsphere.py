import pytest
from mock import mock, Mock
from pyVmomi import vim
from common import secrets

HOST = "test-vcenter-name"


@pytest.fixture(autouse=True)
def monkeypatch_ssm(monkeypatch):
    def mock_return(path):
        return "SECRET"

    monkeypatch.setattr(secrets, "get_parameter", mock_return)


def prefix(obj):
    class_name = type(obj).__name__

    return f"_{class_name}"


def get_protected_value(obj, name):
    class_name = type(obj).__name__

    return getattr(obj, f"_{class_name}__{name}")


@pytest.fixture
def vmware_fixture(get_handler):
    vmware = get_handler("common.clients.vsphere")
    si_mock = Mock()
    return vmware, vmware.VsphereClient(HOST, si=si_mock), si_mock


def test_vmware_client_init(get_handler):
    vmware = get_handler("common.clients.vsphere")

    actual = vmware.VsphereClient(HOST)

    assert get_protected_value(actual, "host") == HOST
    assert get_protected_value(actual, "local_data").si is None


def test_init_connection(vmware_fixture):
    vmware_handler, client, ignore = vmware_fixture

    si_mock = Mock()

    with mock.patch.object(vmware_handler, "connect") as connect_mock:
        # setup
        connect_mock.SmartConnectNoSSL.return_value = si_mock

        # when
        client.init_connection()

        # then
        connect_mock.SmartConnectNoSSL.assert_called_with(
            host=HOST, user="SECRET", pwd="SECRET", port=443
        )

        assert get_protected_value(client, "local_data").si == si_mock


def test_close_connection(vmware_fixture):
    vmware_handler, client, si_mock = vmware_fixture

    with mock.patch.object(vmware_handler, "connect") as connect_mock:
        # when
        client.close_connection()

        # then
        connect_mock.Disconnect.assert_called_with(si_mock)

        assert get_protected_value(client, "local_data").si is None


def test_open_session(vmware_fixture):
    vmware_handler, client, si_mock = vmware_fixture

    with mock.patch.object(
        client, "init_connection"
    ) as init_connection_mock, mock.patch.object(
        client, "close_connection"
    ) as close_connection_mock:
        # when
        with client.open_session():
            pass

        # then
        init_connection_mock.assert_called()
        close_connection_mock.assert_called()


def test_open_session_with_exception(vmware_fixture):
    vmware_handler, client, si_mock = vmware_fixture

    with mock.patch.object(
        client, "init_connection"
    ) as init_connection_mock, mock.patch.object(
        client, "close_connection"
    ) as close_connection_mock:
        # when
        try:
            with client.open_session():
                raise Exception("we do not care")
        except Exception:
            pass

        # then
        init_connection_mock.assert_called()
        close_connection_mock.assert_called()


def test__get_obj(vmware_fixture):
    vmware_handler, client, si_mock = vmware_fixture

    view1 = Mock(vim.View)
    view1.name = "name1"
    view2 = Mock(vim.View)
    view2.name = "name2"
    view3 = Mock(vim.View)
    view3.name = "name3"
    container = Mock(view=[view1, view2, view3])
    view_manager = Mock()
    view_manager.CreateContainerView = Mock(return_value=container)

    si_mock.RetrieveContent.return_value.viewManager = view_manager
    actual = client._get_obj("type", "name1")
    si_mock.RetrieveContent.assert_called()
    assert actual == view1


def test_get_host_system(vmware_fixture):
    vmware_handler, client, si_mock = vmware_fixture

    view1 = Mock(vim.View)
    view1.name = "name1"
    view2 = Mock(vim.View)
    view2.name = "host2"
    view3 = Mock(vim.View)
    view3.name = "name3"
    container = Mock(view=[view1, view2, view3])
    view_manager = Mock()
    view_manager.CreateContainerView = Mock(return_value=container)

    si_mock.RetrieveContent.return_value.viewManager = view_manager
    actual = client.get_host_system("host2")
    si_mock.RetrieveContent.assert_called()
    assert actual == view2


def test_get_host_portgroups(vmware_fixture):
    vmware_handler, client, si_mock = vmware_fixture
    portgroup = Mock()
    view1 = Mock(vim.View)
    view1.name = "host"
    view1.config = Mock(network=Mock(portgroup=portgroup))
    container = Mock(view=[view1])
    view_manager = Mock()
    view_manager.CreateContainerView = Mock(return_value=container)
    si_mock.RetrieveContent.return_value.viewManager = view_manager

    assert client.get_host_portgroups("host") == portgroup


def test_get_host_virtual_switches(vmware_fixture):
    vmware_handler, client, si_mock = vmware_fixture
    vswitch = Mock()
    view1 = Mock(vim.View)
    view1.name = "host"
    view1.config = Mock(network=Mock(vswitch=vswitch))
    container = Mock(view=[view1])
    view_manager = Mock()
    view_manager.CreateContainerView = Mock(return_value=container)
    si_mock.RetrieveContent.return_value.viewManager = view_manager

    assert client.get_host_virtual_switches("host") == vswitch


def test_get_portgroup_by_vswitch(vmware_fixture):
    vmware_handler, client, si_mock = vmware_fixture

    portgroup1 = Mock(vswitch="ab-cd-switch1")
    portgroup2 = Mock(vswitch="ab-cd-switch0")
    portgroup3 = Mock(vswitch="ab-cd-switch2")

    view1 = Mock(vim.View)
    view1.name = "host"
    view1.config = Mock(network=Mock(portgroup=[portgroup1, portgroup2, portgroup3]))
    container = Mock(view=[view1])
    view_manager = Mock()
    view_manager.CreateContainerView = Mock(return_value=container)
    si_mock.RetrieveContent.return_value.viewManager = view_manager

    assert client.get_portgroup_by_vswitch("host", "switch1") == [portgroup1]


def test_do_not_copy(vmware_fixture):
    vmware_handler, client, si_mock = vmware_fixture

    vnic1 = Mock(portgroup="p1")
    vnic2 = Mock(portgroup="p2")
    console_vnic1 = Mock(portgroup="p3")
    console_vnic2 = Mock(portgroup="p4")

    view1 = Mock(vim.View)
    view1.name = "host"
    view1.config = Mock(
        network=Mock(vnic=[vnic1, vnic2], consoleVnic=[console_vnic1, console_vnic2])
    )
    container = Mock(view=[view1])
    view_manager = Mock()
    view_manager.CreateContainerView = Mock(return_value=container)
    si_mock.RetrieveContent.return_value.viewManager = view_manager

    assert client.get_do_not_copy_list("host") == [
        vnic1,
        vnic2,
        console_vnic1,
        console_vnic2,
    ]
    assert client.is_in_do_not_copy_list("host", "p1") is True
    assert client.is_in_do_not_copy_list("host", "p2") is True
    assert client.is_in_do_not_copy_list("host", "p9009") is False


def test_has_portgroup(vmware_fixture):
    vmware_handler, client, si_mock = vmware_fixture

    vnic = Mock()
    spec = Mock()
    spec.name = "p1"
    vnic.spec = spec

    view1 = Mock(vim.View)
    view1.name = "host"
    view1.config = Mock(network=Mock(portgroup=[vnic]))
    container = Mock(view=[view1])
    view_manager = Mock()
    view_manager.CreateContainerView = Mock(return_value=container)
    si_mock.RetrieveContent.return_value.viewManager = view_manager

    assert client.has_portgroup("host", "p1") is True
    assert client.has_portgroup("host", "p187") is False


def test_has_vswitch(vmware_fixture):
    vmware_handler, client, si_mock = vmware_fixture

    switch = Mock()
    switch.name = "s1"

    view1 = Mock(vim.View)
    view1.name = "host"
    view1.config = Mock(network=Mock(vswitch=[switch]))
    container = Mock(view=[view1])
    view_manager = Mock()
    view_manager.CreateContainerView = Mock(return_value=container)
    si_mock.RetrieveContent.return_value.viewManager = view_manager

    assert client.has_virtual_switch("host", "s1") is True
    assert client.has_virtual_switch("host", "s3") is False


def test_add_host_portgroup(vmware_fixture):
    vmware_handler, client, si_mock = vmware_fixture

    view1 = Mock(vim.View)
    view1.name = "host"
    config_manager = Mock()
    network_system = Mock()
    network_system.AddPortGroup = Mock(return_value=Mock())
    config_manager.networkSystem = network_system
    view1.configManager = config_manager
    container = Mock(view=[view1])
    view_manager = Mock()
    view_manager.CreateContainerView = Mock(return_value=container)
    si_mock.RetrieveContent.return_value.viewManager = view_manager
    portgroup_spec = Mock()

    # when
    client.add_host_portgroup("host", portgroup_spec)

    # then
    network_system.AddPortGroup.assert_called_with(portgroup_spec)
