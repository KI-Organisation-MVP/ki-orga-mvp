## Imports
import base64
import json
import logging
import time
import os
from datetime import datetime

from google.cloud import firestore
from google.cloud import pubsub_v1
from google.protobuf import json_format
from google.protobuf.timestamp_pb2 import Timestamp

from kiorga.datamodel import task_pb2
from kiorga.utils.validation import validate_task
from kiorga.utils.monitoring import MetricReporter

class TaskProcessor:
    """
    Kapselt die Geschäftslogik für die Verarbeitung von Tasks.
    """

    def __init__(self, db_client, pub_client, project_id: str, delegation_topic: str, assigned_agent_id: str):
        """
        Initialisiert den TaskProcessor mit den erforderlichen Clients und Konfigurationen.

        Args:
            db_client: Firestore-Client.
            pub_client: Pub/Sub-Publisher-Client.
            project_id: Google Cloud Projekt-ID.
            delegation_topic: Name des Pub/Sub-Topics für die Delegierung.
            assigned_agent_id: ID des Agenten, an den die Aufgabe delegiert wird.
        """
        self.db = db_client
        self.publisher = pub_client
        self.project_id = project_id
        self.delegation_topic = delegation_topic
        self.assigned_agent_id = assigned_agent_id
        self.metric_reporter = MetricReporter(project_id=self.project_id)

    def process_task(self, envelope: dict) -> None:
        """
        Orchestriert den gesamten Prozess der Task-Verarbeitung.
        """
        start_time = time.time()
        try:
            json_string_received, publish_timestamp = self._decode_pubsub_message(envelope)
            receive_latency = time.time() - publish_timestamp
            self.metric_reporter.send_metric("pubsub_message_receive_latency", receive_latency, "GAUGE", "double_value")

            task = self._parse_and_validate_task(json_string_received)

            doc_ref, should_process = self._save_task_to_firestore(task)
            if not should_process:
                return  # Idempotenter Abbruch

            self._delegate_task_to_sda(json_string_received, task.task_id)
            self._update_task_after_delegation(doc_ref, task.task_id)

            processing_time = time.time() - start_time
            self.metric_reporter.send_metric("task_processing_time", processing_time, "GAUGE", "double_value", {"status": "success"})
            logging.info(f"Task {task.task_id} erfolgreich verarbeitet in {processing_time:.4f} Sekunden.")

        except Exception as e:
            self.metric_reporter.send_metric("failed_tasks_count", 1, "CUMULATIVE", "int64_value", {"error_type": type(e).__name__})
            logging.error(f"Fehler bei der Task-Verarbeitung: {e}", exc_info=True)
            raise  # Fehler weiterleiten

    def _decode_pubsub_message(self, envelope: dict) -> tuple[str, float]:
        """Extrahiert und dekodiert die Base64-kodierten Daten aus einer Pub/Sub-Nachricht und gibt den JSON-String und den Publish-Zeitstempel zurück."""
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
            logging.info(f"Empfangene JSON-Daten: {json_string_received}")
            return json_string_received, publish_timestamp
        except Exception as e:
            logging.error(f"Base64-Dekodierung fehlgeschlagen: {e}", exc_info=True)
            raise ValueError("base64 decode error") from e

    def _parse_and_validate_task(self, json_string: str) -> task_pb2.Task:
        """Parst einen JSON-String in ein Task-Objekt und validiert dessen Inhalt."""
        try:
            task = task_pb2.Task()
            json_format.Parse(json_string, task)
            logging.info(f"Successfully parsed Task object from JSON: id={task.task_id}, title='{task.title}'")
        except Exception as e:
            self.metric_reporter.send_metric("task_validation_errors", 1, "CUMULATIVE", "int64_value", {"error_type": type(e).__name__})
            logging.error(f"Protobuf-Deserialisierung fehlgeschlagen: {e}", exc_info=True)
            raise ValueError("protobuf parse error") from e

        validation_errors = validate_task(task)
        if validation_errors:
            error_msg = f"Fehlerhafte Felder: {validation_errors}"
            logging.error(error_msg)
            self._send_metric("task_validation_errors", 1, "CUMULATIVE", "int64_value", {"error_type": "ValidationError"})
            raise ValueError(error_msg)
        
        logging.info("Task-Objekt erfolgreich validiert.")
        return task

    def _save_task_to_firestore(self, task: task_pb2.Task) -> tuple[firestore.DocumentReference, bool]:
        """Speichert den Task in Firestore und prüft auf Idempotenz."""
        try:
            task_dict = json_format.MessageToDict(task)
            doc_ref = self.db.collection("tasks").document(task.task_id)

            task_snapshot = doc_ref.get()
            if task_snapshot.exists and task_snapshot.to_dict().get("assignedToAgentId"):
                logging.warning(f"Task {task.task_id} wurde bereits an {task_snapshot.to_dict().get('assignedToAgentId')} zugewiesen. Breche die Verarbeitung ab.")
                self._send_metric("idempotency_check_hits", 1, "CUMULATIVE", "int64_value", {"reason": "already_assigned"})
                return doc_ref, False

            doc_ref.set(task_dict, merge=True)
            logging.info(f"Task {task.task_id} successfully saved/updated in Firestore.")
            return doc_ref, True
        except Exception as e:
            logging.error(f"Fehler beim Speichern in Firestore: {e}", exc_info=True)
            raise IOError("Firestore write error") from e

    def _delegate_task_to_sda(self, task_json: str, task_id: str):
        """Delegiert den Task an den nächsten Agenten via Pub/Sub."""
        if not task_id:
            logging.warning("Keine Task-ID vorhanden, Delegation wird übersprungen.")
            return

        logging.info(f"Delegating task {task_id} to {self.assigned_agent_id}...")
        try:
            data_to_send = task_json.encode('utf-8')
            topic_path = self.publisher.topic_path(self.project_id, self.delegation_topic)
            future = self.publisher.publish(topic_path, data=data_to_send)
            message_id = future.result(timeout=30)
            logging.info(f"Successfully delegated task to '{self.delegation_topic}' topic. Message ID: {message_id}")
        except Exception as e:
            logging.error(f"Fehler beim Delegieren des Tasks an Pub/Sub: {e}", exc_info=True)
            raise IOError("Pub/Sub publish error") from e

    def _update_task_after_delegation(self, doc_ref, task_id: str):
        """Aktualisiert den Task-Status in Firestore nach der Delegation."""
        try:
            update_data = {
                "status": task_pb2.TaskStatus.TASK_STATUS_IN_PROGRESS,
                "assignedToAgentId": self.assigned_agent_id,
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            doc_ref.update(update_data)
            logging.info(f"Task {task_id} status updated to IN_PROGRESS and assigned to {self.assigned_agent_id}.")
        except Exception as e:
            logging.error(f"Fehler beim Aktualisieren des Tasks in Firestore: {e}", exc_info=True)
            raise IOError("Firestore update error") from e
