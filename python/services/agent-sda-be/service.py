import base64
import json
import logging
import time
import uuid
import os
from datetime import datetime

from google.cloud import firestore
from google.cloud import pubsub_v1
from google.cloud import monitoring_v3
from google.protobuf import json_format
from google.protobuf.timestamp_pb2 import Timestamp

from kiorga.datamodel import final_report_pb2, task_pb2
from kiorga.datamodel.final_report_pb2 import FinalStatus
from kiorga.datamodel.task_pb2 import TaskStatus


class TaskHandler:
    """
    Kapselt die Geschäftslogik für die Verarbeitung von Tasks durch den SDA-BE-Agenten.
    """

    def __init__(self, db_client, pub_client, project_id: str, agent_id: str, reports_topic: str):
        self.db = db_client
        self.publisher = pub_client
        self.project_id = project_id
        self.agent_id = agent_id
        self.reports_topic = reports_topic
        self.monitoring_client = monitoring_v3.MetricServiceClient()

    def _send_metric(self, metric_type: str, value: float, metric_kind: str, value_type: str, labels: dict = None):
        """
        Sendet eine benutzerdefinierte Metrik an Google Cloud Monitoring.
        """
        series = monitoring_v3.TimeSeries()
        series.metric.type = f"custom.googleapis.com/{metric_type}"
        if labels:
            for key, val in labels.items():
                series.metric.labels[key] = val

        now = time.time()
        seconds = int(now)
        nanos = int((now - seconds) * 10**9)
        interval = monitoring_v3.TimeInterval(
            end_time=monitoring_v3.Timestamp(seconds=seconds, nanos=nanos)
        )

        point = monitoring_v3.Point(
            interval=interval,
            **{f"value": monitoring_v3.TypedValue(**{value_type: value})}
        )
        series.points.append(point)

        series.resource.type = "cloud_run_revision"
        series.resource.labels["project_id"] = self.project_id
        series.resource.labels["service_name"] = os.environ.get("K_SERVICE", "agent-sda-be-service")
        series.resource.labels["revision_name"] = os.environ.get("K_REVISION", "latest")
        series.resource.labels["location"] = os.environ.get("K_LOCATION", "europe-west3")

        try:
            self.monitoring_client.create_time_series(name=f"projects/{self.project_id}", time_series=[series])
            logging.info(f"Metrik '{metric_type}' mit Wert {value} gesendet.")
        except Exception as e:
            logging.error(f"Fehler beim Senden der Metrik '{metric_type}': {e}", exc_info=True)

    def handle_task(self, envelope: dict):
        """
        Orchestriert den gesamten Prozess der Task-Verarbeitung.
        """
        task = None
        start_time = time.time()
        try:
            task, publish_timestamp = self._parse_task_from_request(envelope)
            receive_latency = time.time() - publish_timestamp
            self._send_metric("pubsub_message_receive_latency", receive_latency, "GAUGE", "double_value")

            if self._check_idempotency(task.task_id):
                return

            self._update_task_status(task.task_id, TaskStatus.TASK_STATUS_IN_PROGRESS)
            self._perform_simulated_work(task.task_id)
            self._create_and_publish_final_report(task.task_id)
            self._update_task_status(task.task_id, TaskStatus.TASK_STATUS_COMPLETED)

            processing_time = time.time() - start_time
            self._send_metric("task_processing_time", processing_time, "GAUGE", "double_value", {"status": "success"})
            logging.info(f"Task {task.task_id} erfolgreich verarbeitet in {processing_time:.4f} Sekunden.")

        except (ValueError, IOError) as e:
            self._send_metric("failed_tasks_count", 1, "CUMULATIVE", "int64_value", {"error_type": type(e).__name__})
            raise e
        except Exception as e:
            logging.error(f"Unerwarteter Fehler bei der Verarbeitung von Task {getattr(task, 'task_id', 'N/A')}: {e}", exc_info=True)
            if task and task.task_id:
                self._update_task_status(task.task_id, TaskStatus.TASK_STATUS_FAILED)
            self._send_metric("failed_tasks_count", 1, "CUMULATIVE", "int64_value", {"error_type": type(e).__name__})
            raise IOError("Unbekannter interner Fehler") from e

    def _parse_task_from_request(self, envelope: dict) -> tuple[task_pb2.Task, float]:
        """Extrahiert, dekodiert und parst den Task aus der Pub/Sub-Nachricht und gibt den Task und den Publish-Zeitstempel zurück."""
        if not isinstance(envelope, dict) or "message" not in envelope:
            raise ValueError("invalid Pub/Sub message format")

        pubsub_message = envelope["message"]
        if not isinstance(pubsub_message, dict) or "data" not in pubsub_message:
            raise ValueError("Pub/Sub message missing 'data' field")

        publish_time_str = pubsub_message.get("publish_time")
        publish_timestamp = 0.0
        if publish_time_str:
            try:
                dt_object = datetime.fromisoformat(publish_time_str.replace('Z', '+00:00'))
                publish_timestamp = dt_object.timestamp()
            except ValueError:
                logging.warning(f"Konnte publish_time '{publish_time_str}' nicht parsen.")
                publish_timestamp = time.time() # Fallback zu aktueller Zeit
        else:
            publish_timestamp = time.time() # Fallback zu aktueller Zeit

        try:
            data_bytes = base64.b64decode(pubsub_message["data"])
            json_string_received = data_bytes.decode('utf-8')
            task = task_pb2.Task()
            json_format.Parse(json_string_received, task)
            logging.info(f"SDA-BE received task: id={task.task_id}, title='{task.title}'")
            return task, publish_timestamp
        except Exception as e:
            self._send_metric("task_validation_errors", 1, "CUMULATIVE", "int64_value", {"error_type": type(e).__name__})
            logging.error(f"Fehler beim Parsen des Tasks: {e}", exc_info=True)
            raise ValueError("could not parse task from message") from e

    def _check_idempotency(self, task_id: str) -> bool:
        """Prüft, ob bereits ein Abschlussbericht für den Task existiert."""
        reports_ref = self.db.collection("final_reports")
        query = reports_ref.where("taskId", "==", task_id).limit(1)
        if list(query.stream()):
            logging.warning(f"Task {task_id} wurde bereits abgeschlossen. Breche Verarbeitung ab.")
            self._send_metric("idempotency_check_hits", 1, "CUMULATIVE", "int64_value", {"reason": "already_completed"})
            return True
        return False

    def _update_task_status(self, task_id: str, status: TaskStatus):
        """Aktualisiert den Status eines Tasks in Firestore."""
        try:
            task_doc_ref = self.db.collection("tasks").document(task_id)
            task_doc_ref.update({"status": status})
            logging.info(f"Task {task_id} status updated to {TaskStatus.Name(status)}.")
        except Exception as e:
            logging.error(f"Konnte Task-Status für {task_id} nicht aktualisieren: {e}", exc_info=True)
            # In einem realen Szenario könnte hier ein robusterer Fehler-Handler stehen.

    def _perform_simulated_work(self, task_id: str):
        """Simuliert die eigentliche Arbeit des Agenten."""
        logging.info(f"Starting work on task {task_id}...")
        time.sleep(2)
        logging.info(f"Work on task {task_id} finished.")

    def _create_and_publish_final_report(self, task_id: str):
        """Erstellt, speichert und veröffentlicht einen Abschlussbericht."""
        report_id = str(uuid.uuid4())
        now = Timestamp()
        now.GetCurrentTime()

        final_report = final_report_pb2.FinalReport(
            report_id=report_id,
            task_id=task_id,
            executing_agent_id=self.agent_id,
            final_status=FinalStatus.FINAL_STATUS_SUCCESS,
            summary="SDA-BE has successfully completed the simulated task.",
            completion_timestamp=now
        )

        try:
            report_dict = json_format.MessageToDict(final_report)
            self.db.collection("final_reports").document(report_id).set(report_dict)
            logging.info(f"FinalReport {report_id} for task {task_id} saved to Firestore.")

            report_json_string = json.dumps(report_dict)
            report_bytes = report_json_string.encode('utf-8')
            topic_path = self.publisher.topic_path(self.project_id, self.reports_topic)
            future = self.publisher.publish(topic_path, data=report_bytes)
            future.result(timeout=30)
            logging.info(f"Published FinalReport {report_id} for task {task_id} to Pub/Sub.")
        except Exception as e:
            logging.error(f"Fehler beim Speichern/Veröffentlichen des Berichts für Task {task_id}: {e}", exc_info=True)
            raise IOError("could not persist or publish final report") from e
