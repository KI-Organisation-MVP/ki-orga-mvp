import logging
import os
import time

from google.cloud import monitoring_v3
from google.cloud.monitoring_v3 import types


class MetricReporter:
    """
    A centralized utility for sending custom metrics to Google Cloud Monitoring.
    """

    def __init__(self, project_id: str, client: monitoring_v3.MetricServiceClient = None):
        """
        Initializes the MetricReporter.

        Args:
            project_id: The Google Cloud Project ID.
            client: An optional, pre-configured MetricServiceClient. If None, a new one is created.
        """
        self.project_id = project_id
        self.client = client or monitoring_v3.MetricServiceClient()

    def send_metric(self, metric_type: str, value: float, metric_kind: str, value_type: str, labels: dict = None):
        """
        Constructs and sends a single time series data point to Cloud Monitoring.
        """
        # Verwenden Sie 'types' für alle Datenstrukturen, um Konsistenz zu gewährleisten
        # und Fehler wie "AttributeError: module 'google.cloud.monitoring_v3' has no attribute 'Metric'" zu vermeiden.
        series = types.TimeSeries()
        series.metric.type = f"custom.googleapis.com/{metric_type}"
        # KORREKTUR 1: MetricKind und ValueType sind Enums innerhalb von MetricDescriptor.
        # Wir greifen über das Hauptmodul `monitoring_v3` darauf zu, um Stabilität zu gewährleisten.
        series.metric_kind = monitoring_v3.MetricDescriptor.MetricKind[metric_kind.upper()]
        # KORREKTUR 2: Der ValueType muss ebenfalls auf der TimeSeries gesetzt werden,
        # damit die API den Typ des Datenpunktes kennt.
        series.value_type = monitoring_v3.MetricDescriptor.ValueType[value_type.upper()]
        if labels:
            for key, val in labels.items():
                series.metric.labels[key] = val

        series.resource.type = "cloud_run_revision"
        series.resource.labels["project_id"] = self.project_id
        series.resource.labels["service_name"] = os.environ.get("K_SERVICE", "unknown-service")
        series.resource.labels["revision_name"] = os.environ.get("K_REVISION", "unknown-revision")
        series.resource.labels["location"] = os.environ.get("K_LOCATION", "unknown-location")

        now = time.time()
        seconds = int(now)
        nanos = int((now - seconds) * 10**9)
        interval = types.TimeInterval(end_time=types.Timestamp(seconds=seconds, nanos=nanos))

        point = types.Point(interval=interval, value=types.TypedValue(**{value_type: value}))
        series.points.append(point)

        try:
            self.client.create_time_series(name=f"projects/{self.project_id}", time_series=[series])
            logging.info(f"Metric '{metric_type}' with value {value} sent.")
        except Exception as e:
            logging.error(f"Failed to send metric '{metric_type}': {e}", exc_info=True)