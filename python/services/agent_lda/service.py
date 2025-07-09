## Imports
import logging
import time

from google.cloud import firestore
from google.protobuf import json_format

from kiorga.datamodel import task_pb2
from kiorga.utils.validation import parse_and_validate_message, validate_task
from kiorga.utils.pubsub_helpers import decode_pubsub_message, publish_proto_message_as_json

class TaskHandler:
    """
    Kapselt die Geschäftslogik für die Verarbeitung von Tasks.
    """

    def __init__(self, db_client, pub_client, project_id: str, delegation_topic: str, assigned_agent_id: str):
        """
        Initialisiert den TaskHandler mit den erforderlichen Clients und Konfigurationen.

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

    def handle_task(self, envelope: dict) -> None:
        """
        Orchestriert den gesamten Prozess der Task-Verarbeitung.
        """
        start_time = time.time()
        try:
            json_string_received, publish_timestamp = decode_pubsub_message(envelope)
            # receive_latency = time.time() - publish_timestamp # Metrik entfernt

            task = parse_and_validate_message(
                json_string=json_string_received,
                message_class=task_pb2.Task,
                validator_func=validate_task
            )

            doc_ref, should_process = self._save_task_to_firestore(task)
            if not should_process:
                return  # Idempotenter Abbruch

            self._delegate_task_to_sda(task)
            self._update_task_after_delegation(doc_ref, task.task_id)

            logging.info(f"Task {task.task_id} erfolgreich verarbeitet.")

        except Exception as e:
            logging.error(f"Fehler bei der Task-Verarbeitung: {e}", exc_info=True)
            raise  # Fehler weiterleiten

    def _save_task_to_firestore(self, task: task_pb2.Task) -> tuple[firestore.DocumentReference, bool]:
        """Speichert den Task in Firestore und prüft auf Idempotenz."""
        try:
            task_dict = json_format.MessageToDict(task)
            doc_ref = self.db.collection("tasks").document(task.task_id)

            task_snapshot = doc_ref.get()
            if task_snapshot.exists and task_snapshot.to_dict().get("assignedToAgentId"):
                logging.warning(f"Task {task.task_id} wurde bereits an {task_snapshot.to_dict().get('assignedToAgentId')} zugewiesen. Breche die Verarbeitung ab.")
                return doc_ref, False

            doc_ref.set(task_dict, merge=True)
            logging.info(f"Task {task.task_id} successfully saved/updated in Firestore.")
            return doc_ref, True
        except Exception as e:
            logging.error(f"Fehler beim Speichern in Firestore: {e}", exc_info=True)
            raise IOError("Firestore write error") from e

    def _delegate_task_to_sda(self, task: task_pb2.Task):
        """Delegiert den Task an den nächsten Agenten via Pub/Sub."""
        if not task.task_id:
            logging.warning("Keine Task-ID vorhanden, Delegation wird übersprungen.")
            return

        logging.info(f"Delegating task {task.task_id} to {self.assigned_agent_id} via topic '{self.delegation_topic}'...")
        try:
            publish_proto_message_as_json(
                publisher=self.publisher,
                project_id=self.project_id,
                topic_id=self.delegation_topic,
                proto_message=task
            )
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
