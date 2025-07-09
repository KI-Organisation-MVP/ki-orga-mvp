import logging
import time
import uuid

from google.protobuf import json_format
from google.protobuf.timestamp_pb2 import Timestamp

from kiorga.datamodel import final_report_pb2, task_pb2
from kiorga.utils.pubsub_helpers import decode_pubsub_message, publish_proto_message_as_json
from kiorga.utils.validation import parse_and_validate_message


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

    def handle_task(self, envelope: dict):
        """
        Orchestriert den gesamten Prozess der Task-Verarbeitung.
        """
        task = None
        start_time = time.time()
        try:
            json_string_received, publish_timestamp = decode_pubsub_message(envelope)
            # receive_latency = time.time() - publish_timestamp # Metrik entfernt

            task = parse_and_validate_message(
                json_string=json_string_received,
                message_class=task_pb2.Task
            )
            logging.info(f"SDA-BE received task: id={task.task_id}, title='{task.title}'")

            if self._check_idempotency(task.task_id):
                return

            self._update_task_status(task.task_id, task_pb2.TaskStatus.TASK_STATUS_IN_PROGRESS)
            self._perform_simulated_work(task.task_id)
            self._create_and_publish_final_report(task.task_id)
            self._update_task_status(task.task_id, task_pb2.TaskStatus.TASK_STATUS_COMPLETED)

            processing_time = time.time() - start_time
            logging.info(f"Task {task.task_id} erfolgreich verarbeitet in {processing_time:.4f} Sekunden.")

        except (ValueError, IOError) as e:
            raise e
        except Exception as e:
            logging.error(f"Unerwarteter Fehler bei der Verarbeitung von Task {getattr(task, 'task_id', 'N/A')}: {e}", exc_info=True)
            if task and task.task_id:
                self._update_task_status(task.task_id, task_pb2.TaskStatus.TASK_STATUS_FAILED)
            raise IOError("Unbekannter interner Fehler") from e

    def _check_idempotency(self, task_id: str) -> bool:
        """Prüft, ob bereits ein Abschlussbericht für den Task existiert."""
        reports_ref = self.db.collection("final_reports")
        query = reports_ref.where("taskId", "==", task_id).limit(1)
        if list(query.stream()):
            logging.warning(f"Task {task_id} wurde bereits abgeschlossen. Breche Verarbeitung ab.")
            return True
        return False

    def _update_task_status(self, task_id: str, status: task_pb2.TaskStatus):
        """Aktualisiert den Status eines Tasks in Firestore."""
        try:
            task_doc_ref = self.db.collection("tasks").document(task_id)
            task_doc_ref.update({"status": status})
            logging.info(f"Task {task_id} status updated to {task_pb2.TaskStatus.Name(status)}.")
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
            final_status=final_report_pb2.FinalStatus.FINAL_STATUS_SUCCESS,
            summary="SDA-BE has successfully completed the simulated task.",
            completion_timestamp=now
        )

        try:
            report_dict = json_format.MessageToDict(final_report)
            self.db.collection("final_reports").document(report_id).set(report_dict)
            logging.info(f"FinalReport {report_id} for task {task_id} saved to Firestore.")

            publish_proto_message_as_json(
                publisher=self.publisher,
                project_id=self.project_id,
                topic_id=self.reports_topic,
                proto_message=final_report
            )
        except Exception as e:
            logging.error(f"Fehler beim Speichern/Veröffentlichen des Berichts für Task {task_id}: {e}", exc_info=True)
            raise IOError("could not persist or publish final report") from e
