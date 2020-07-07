import os
from datetime import datetime
import json
from enum import Enum
from common import log
from pynamodb.models import Model
from pynamodb.attributes import UnicodeAttribute, NumberAttribute, MapAttribute
from pynamodb.constants import STREAM_OLD_IMAGE
from pynamodb.exceptions import DoesNotExist


logger = log.setup_logging()


REGION = "us-west-2"
TABLE_NAME = f"{os.environ.get('STAGE', 'dev')}-goss-api-metrics.v1"


class MetricType(Enum):
    MONITORING = "monitoring"
    PATCHING = "patching"


class OsType(Enum):
    WINDOWS = "windows"
    LINUX = "linux"


# Example Monitoring payload:
# {
#   "windows": {
#     "alarms_disk_free_space": {
#       "threshold": 256,
#       "period": 55
#     },
#     "alarms_disk_used_percent": {
#       "threshold": 95,
#       "period": 240
#     },
#     "alarms_memory": {
#       "threshold": 90,
#       "period": 150
#     },
#     "alarms_cpu": {
#       "threshold": 85,
#       "period": 200
#     }
#   },
#   "linux": {
#     "alarms_disk_free_space": {
#       "threshold": 524288006,
#       "period": 55
#     },
#     "alarms_disk_used_percent": {
#       "threshold": 95,
#       "period": 240
#     },
#     "alarms_memory": {
#       "threshold": 90,
#       "period": 150
#     },
#     "alarms_cpu": {
#       "threshold": 85,
#       "period": 200
#     }
#   }
# }


class BaseMetricsModel(Model):
    class Meta:
        table_name = TABLE_NAME
        region = REGION
        stream_view_type = STREAM_OLD_IMAGE

    # Combination of vcenter name and metric type
    metric_id = UnicodeAttribute(hash_key=True)
    os_type = UnicodeAttribute(range_key=True)

    # Pulled from https://github.com/pynamodb/PynamoDB/issues/152
    def to_json(self, indent=2):
        return json.dumps(self.to_dict(), indent=indent)

    def to_dict(self):
        ret_dict = {}
        for name, attr in self.attribute_values.items():
            ret_dict[name] = self._attr2obj(attr)

        return ret_dict

    def _attr2obj(self, attr):
        # compare with list class. It is not ListAttribute.
        if isinstance(attr, list):
            _list = []
            for l in attr:
                _list.append(self._attr2obj(l))
            return _list
        elif isinstance(attr, MapAttribute):
            _dict = {}
            for k, v in attr.attribute_values.items():
                _dict[k] = self._attr2obj(v)
            return _dict
        elif isinstance(attr, datetime):
            return attr.isoformat()
        else:
            return attr


class MonitoringAttribute(MapAttribute):
    threshold = NumberAttribute()
    period = NumberAttribute()


class MonitoringMetricsModel(BaseMetricsModel):
    class Meta:
        table_name = TABLE_NAME
        region = REGION
        stream_view_type = STREAM_OLD_IMAGE

    os_type = UnicodeAttribute(range_key=True)
    alarms_disk_free_space = MonitoringAttribute()
    alarms_disk_used_percent = MonitoringAttribute()
    alarms_memory = MonitoringAttribute()
    alarms_cpu = MonitoringAttribute()


class Metrics(object):
    def _make_key(self, metric_type, vcenter):
        """
        Creates a combined key from the Arguments to be used as the id

        Arguments:
            vcenter (string): The name of the vCenter
            metric_type (string): The type of metric being stored

        Returns:
            string: The combined value of metric_type_vcenter
        """
        return f"{metric_type}_{vcenter}"

    def _validate_os(self, os_type):
        """
        Checks to make sure OS is either windows or linux.
        """
        if os_type not in [os.value for os in OsType]:
            msg = f"os_type must be one of {[os.value for os in OsType]}"
            raise ValueError(msg)


class MonitoringMetrics(Metrics):
    def create(self, vcenter, metrics):
        """
        Creates an entry for the given metrics in the ddb.

        Arguments:
            vcenter (string): The name of the vCenter
            metrics (dict): Metric information

        Returns:
            dict: The metrics that were stored.

        Raises:
            ValueError: OS is invalid

        Note: No error is thrown if metrics already exist, they will NOT get overwritten
        """
        logger.debug(f"Creating metrics for {vcenter}")
        metrics_model = MonitoringMetricsModel(
            metric_id=self._make_key(MetricType.MONITORING.value, vcenter)
        )

        for os_type in metrics:  # os should either be windows or linux
            self._validate_os(os_type)

            # Make sure that metrics don't already exist for this OS for this vCenter
            existing_metrics = self.readByOs(vcenter, os_type)
            if existing_metrics is not None:
                msg = f"Monitoring metrics already exist for {vcenter} - {os_type}. Not going to update."
                logger.debug(msg)
                raise AttributeError(msg)

            metrics_model.os_type = os_type
            metrics_model.alarms_disk_free_space = metrics[os_type].get(
                "alarms_disk_free_space", {}
            )
            metrics_model.alarms_disk_used_percent = metrics[os_type].get(
                "alarms_disk_used_percent", {}
            )
            metrics_model.alarms_memory = metrics[os_type].get("alarms_memory", {})
            metrics_model.alarms_cpu = metrics[os_type].get("alarms_cpu", {})
            metrics_model.save()

        return self.read(vcenter)

    def read(self, vcenter):
        """
        Find metrics based on the vcenter.

        Arguments:
            vcenter (string): The name of the vCenter

        Returns:
            None: When no metrics can be found for the given type
            string: List of metrics
        """
        try:
            logger.debug(f"Retrieving metrics for {vcenter}")
            results = MonitoringMetricsModel.query(
                self._make_key(MetricType.MONITORING.value, vcenter)
            )

            # To hold the results
            all_metrics = []

            for index, metrics in enumerate(results):
                all_metrics.append(metrics.to_dict())
        except DoesNotExist:
            return None

        return all_metrics

    def readByOs(self, vcenter, os_type):
        """
        Find metrics based on the vcenter and the os type.

        Arguments:
            vcenter (string): The name of the vCenter
            os_type (string): The type of OS this metric belongs to OsType

        Returns:
            None: When no metrics can be found for the given type
            string: The metrics content
        """
        logger.debug(f"Retrieving metrics for {vcenter} and {os_type}")
        for metrics in MonitoringMetricsModel.query(
            self._make_key(MetricType.MONITORING.value, vcenter),
            MonitoringMetricsModel.os_type.__eq__(os_type),
        ):
            return metrics

    def update(self, vcenter, metrics):
        """
        Update the metrics contents for the given metrics type. Only the metrics are changeable.

        Arguments:
            vcenter (string): The name of the vCenter.
            metrics (dict): The new metric values for the given type

        Returns:
            list: The metrics

        Raises:
            ValueError: When asked to update metrics that do not exist
        """
        logger.debug(f"Updating metrics for {vcenter}")
        for os_type in metrics:  # os should either be windows or linux
            self._validate_os(os_type)

            # Get exiting value
            existing_metrics = self.readByOs(vcenter, os_type)
            if existing_metrics is None:
                raise ValueError(f"No metrics found for {vcenter} and {os_type}")

            # We only want to update metrics that have been passed in
            actions_list = []

            if metrics[os_type].get("alarms_disk_free_space") is not None:
                actions_list.append(
                    MonitoringMetricsModel.alarms_disk_free_space.set(
                        metrics[os_type].get("alarms_disk_free_space")
                    )
                )
            elif metrics[os_type].get("alarms_disk_used_percent") is not None:
                actions_list.append(
                    MonitoringMetricsModel.alarms_disk_used_percent.set(
                        metrics[os_type].get("alarms_disk_used_percent")
                    )
                )
            elif metrics[os_type].get("alarms_memory") is not None:
                actions_list.append(
                    MonitoringMetricsModel.alarms_memory.set(
                        metrics[os_type].get("alarms_memory")
                    )
                )
            elif metrics[os_type].get("alarms_cpu") is not None:
                actions_list.append(
                    MonitoringMetricsModel.alarms_cpu.set(
                        metrics[os_type].get("alarms_cpu")
                    )
                )
            else:
                logger.debug(f"No updates provided for {os_type} in {vcenter}")

            existing_metrics.update(actions=actions_list)

        return self.read(vcenter)

    def delete(self, vcenter):
        """
        Purge the metrics in question.

        Arguments:
            vcenter (string): The name of the vCenter

        Returns:
            None: No takesies backsies
        """
        logger.debug(f"Deleting metrics for {vcenter}")
        for metrics in MonitoringMetricsModel.query(
            self._make_key(MetricType.MONITORING.value, vcenter)
        ):
            metrics.delete()

        return None
