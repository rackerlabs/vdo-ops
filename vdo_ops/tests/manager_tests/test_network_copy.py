import pytest
import mock
from mock import patch, Mock
from common import secrets
from tests.helper import util

TARGET_MODULE = "managers.network_copy.network_copy"


@pytest.fixture(autouse=True)
def monkeypatch_ssm(monkeypatch):
    def mock_return(path):
        return "SECRET"

    monkeypatch.setattr(secrets, "get_parameter", mock_return)


@patch(f"{TARGET_MODULE}.CLIENTS")
def test_lambda_handler(clients_mock, get_handler):
    lambda_handler = get_handler(TARGET_MODULE)

    # setup
    event = {
        "from_device": "364027",
        "to_device": "364026",
    }

    hyp_data_1 = util.load_json_file("data/zamboni/get_host_system.json")
    hyp_data_2 = util.load_json_file("data/zamboni/get_host_system_2.json")
    zamboni_client_mock = Mock(
        **{
            "get_hyps_by_device_id.side_effect": [
                hyp_data_1.get("data")[0],
                hyp_data_2.get("data")[0],
            ]
        }
    )
    clients_mock.zamboni_client = zamboni_client_mock

    vsphere_mock = mock.Mock()
    vsphere_mock.copy_networks.return_value = Mock()

    # when
    with mock.patch.object(lambda_handler, "VsphereApi", return_value=vsphere_mock):
        lambda_handler.handler(event, None)

        # then
        vsphere_mock.copy_networks.assert_called_with(
            "364027-hyp90.ord1.rvi.local", "364026-hyp90.ord1.rvi.local"
        )


@patch(f"{TARGET_MODULE}.CLIENTS")
def test_lambda_handler_vcenter_login(clients_mock, get_handler):
    lambda_handler = get_handler(TARGET_MODULE)

    # setup
    event = {
        "from_device": "364027",
        "to_device": "364026",
    }

    hyp_data_1 = util.load_json_file("data/zamboni/get_host_system.json")
    hyp_data_2 = util.load_json_file("data/zamboni/get_host_system_2.json")
    zamboni_client_mock = Mock(
        **{
            "get_hyps_by_device_id.side_effect": [
                hyp_data_1.get("data")[0],
                hyp_data_2.get("data")[0],
            ]
        }
    )
    clients_mock.zamboni_client = zamboni_client_mock

    vsphere_mock = mock.Mock()
    vsphere_mock.side_effect = Exception("Boom!")

    # when
    with mock.patch.object(lambda_handler, "VsphereApi", side_effect=vsphere_mock):
        with pytest.raises(Exception):
            lambda_handler.handler(event, None)


@patch(f"{TARGET_MODULE}.CLIENTS")
def test_lambda_handler_copy_error(clients_mock, get_handler):
    lambda_handler = get_handler(TARGET_MODULE)

    # setup
    event = {
        "from_device": "364027",
        "to_device": "364026",
    }

    hyp_data_1 = util.load_json_file("data/zamboni/get_host_system.json")
    hyp_data_2 = util.load_json_file("data/zamboni/get_host_system_2.json")
    zamboni_client_mock = Mock(
        **{
            "get_hyps_by_device_id.side_effect": [
                hyp_data_1.get("data")[0],
                hyp_data_2.get("data")[0],
            ]
        }
    )
    clients_mock.zamboni_client = zamboni_client_mock

    vsphere_mock = mock.Mock()
    vsphere_mock.copy_networks.side_effect = Exception("Boom!")

    # when
    with mock.patch.object(lambda_handler, "VsphereApi", return_value=vsphere_mock):
        with pytest.raises(Exception):
            lambda_handler.handler(event, None)
