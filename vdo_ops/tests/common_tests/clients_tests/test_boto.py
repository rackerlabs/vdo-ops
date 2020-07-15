import mock
import pytest

from common import constants
from common.clients.boto import ClientType


def test_get_boto_session(get_handler):
    boto = get_handler("common.clients.boto")

    def fake_session(**kwargs):
        return kwargs

    with mock.patch.object(boto.boto3, "Session", mock.Mock(side_effect=fake_session)):
        assert boto.get_boto_session() == {"region_name": "us-west-2"}


def test_get_client(get_handler):
    class FakeClient:
        def client(self, client_name):
            return client_name

    boto = get_handler("common.clients.boto")
    with mock.patch.object(boto, "get_boto_session", FakeClient):
        assert boto.get_client(ClientType.STEP_FUNCTIONS) == "stepfunctions"


def test_make_arn(get_handler):
    boto = get_handler("common.clients.boto")

    class FakeSTS:
        def get_caller_identity(*args, **kwargs):
            return {"Account": "12345"}

    with mock.patch.object(boto, "get_client", return_value=FakeSTS()):
        test_arn = boto.make_arn("foo", "bar")
        assert test_arn == "arn:aws:foo:us-west-2:12345:bar"


def test_make_host_name(get_handler):
    boto = get_handler("common.clients.boto")
    resp = boto.make_host_name("foo.bar", "12345")
    assert resp == "foo.bar.12345.dev.rpc-v.rackspace-cloud.com."


def test_manage_dns_record(get_handler):
    boto = get_handler("common.clients.boto")
    mock_r53 = mock.Mock()
    mock_r53.change_resource_record_sets.return_value = None
    request = {
        "HostedZoneId": constants.CUSTOMER_DNS_ZONE_ID,
        "ChangeBatch": {
            "Changes": [
                {
                    "Action": boto.Route53Actions.CREATE.value,
                    "ResourceRecordSet": {
                        "Name": "foo.bar",
                        "Type": boto.Route53RecordTypes.A.value,
                        "TTL": 60,
                        "ResourceRecords": [{"Value": "127.0.0.1"}],
                    },
                }
            ]
        },
    }
    with mock.patch.object(boto, "get_client", return_value=mock_r53) as mock_boto:
        resp1 = boto.manage_dns_record(
            "foo.bar",
            "127.0.0.1",
            action=boto.Route53Actions.CREATE,
            record_type=boto.Route53RecordTypes.A,
            ttl=60,
        )
        mock_r53.change_resource_record_sets.assert_called_with(**request)
        mock_boto.assert_called_with(boto.ClientType.ROUTE53)
        assert resp1 is None


def test_initiate_batch_job(get_handler):
    boto_handler = get_handler("common.clients.boto")

    batch_client_mock = mock.Mock()

    job_queues = {
        "jobQueues": [
            {"jobQueueName": "test-job_queue1", "jobQueueArn": "jobQueueArn1"},
            {"jobQueueName": "test-job_queue2", "jobQueueArn": "jobQueueArn1"},
        ],
    }
    job_definitions = {
        "jobDefinitions": [
            {
                "jobDefinitionName": "test-job_def1",
                "jobDefinitionArn": "jobDefinitionArn1",
            },
            {
                "jobDefinitionName": "test-job_def2",
                "jobDefinitionArn": "jobDefinitionArn1",
            },
        ],
    }
    params = {"name": "name1", "city": "san antonio"}

    with mock.patch.object(
        boto_handler, "get_client", return_value=batch_client_mock
    ), mock.patch.object(
        batch_client_mock, "describe_job_queues", return_value=job_queues
    ), mock.patch.object(
        batch_client_mock, "describe_job_definitions", return_value=job_definitions
    ), mock.patch.object(
        batch_client_mock, "submit_job", return_value={"jobId": "job-123"}
    ):
        job_id = boto_handler.initiate_batch_job(
            "job_name1", "job_queue1", "job_def1", params
        )
        assert job_id == "job-123"

        boto_handler.get_client.assert_called_with(boto_handler.ClientType.BATCH)
        batch_client_mock.describe_job_queues.assert_called_once()
        batch_client_mock.describe_job_definitions.assert_called_once()
        batch_client_mock.submit_job.assert_called_with(
            jobName="job_name1",
            jobQueue="test-job_queue1",
            jobDefinition="test-job_def1",
            parameters=params,
        )


def test_check_batch_job_status_succeeded(get_handler):
    boto_handler = get_handler("common.clients.boto")

    batch_client_mock = mock.Mock()

    jobs = {"jobs": [{"jobId": "job_name-123", "status": "SUCCEEDED"}]}

    with mock.patch.object(
        boto_handler, "get_client", return_value=batch_client_mock
    ), mock.patch.object(batch_client_mock, "describe_jobs", return_value=jobs):
        status = boto_handler.check_batch_job_status("job_name-123")
        assert status

        boto_handler.get_client.assert_called_with(boto_handler.ClientType.BATCH)
        batch_client_mock.describe_jobs.assert_called_with(jobs=["job_name-123"])


def test_check_batch_job_status_failed(get_handler):
    boto_handler = get_handler("common.clients.boto")

    batch_client_mock = mock.Mock()

    jobs = {"jobs": [{"jobId": "job_name-123", "status": "FAILED"}]}

    with mock.patch.object(
        boto_handler, "get_client", return_value=batch_client_mock
    ), mock.patch.object(batch_client_mock, "describe_jobs", return_value=jobs):
        with pytest.raises(boto_handler.TaskFailureException, match="status=FAILED"):
            boto_handler.check_batch_job_status("job_name-123")

            boto_handler.get_client.assert_called_with(boto_handler.ClientType.BATCH)
            batch_client_mock.describe_jobs.assert_called_with(jobs=["job_name-123"])


def test_check_batch_job_status_running(get_handler):
    boto_handler = get_handler("common.clients.boto")

    batch_client_mock = mock.Mock()

    jobs = {"jobs": [{"jobId": "job_name-123", "status": "RUNNING"}]}

    with mock.patch.object(
        boto_handler, "get_client", return_value=batch_client_mock
    ), mock.patch.object(batch_client_mock, "describe_jobs", return_value=jobs):
        status = boto_handler.check_batch_job_status("job_name-123")
        assert not status

        boto_handler.get_client.assert_called_with(boto_handler.ClientType.BATCH)
        batch_client_mock.describe_jobs.assert_called_with(jobs=["job_name-123"])


def test_get_state_machine_status(get_handler):
    boto_handler = get_handler("common.clients.boto")

    batch_client_mock = mock.Mock()

    with mock.patch.object(
        boto_handler, "get_client", return_value=batch_client_mock
    ), mock.patch.object(
        batch_client_mock, "describe_execution", return_value={"status": "RUNNING"}
    ):
        status = boto_handler.get_state_machine_status("execution_arn")
        assert status == boto_handler.StepfunctionStatus.RUNNING.value

        batch_client_mock.describe_execution.assert_called_with(
            executionArn="execution_arn"
        )
