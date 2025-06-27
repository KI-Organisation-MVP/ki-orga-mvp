import os
import base64
import json
import logging
import uuid
import time

from flask import Flask, request

from google.cloud import firestore
from google.cloud import pubsub_v1
from google.protobuf import json_format
from google.protobuf.timestamp_pb2 import Timestamp

from kiorga.datamodel import task_pb2
from kiorga.datamodel import final_report_pb2
from kiorga.datamodel.task_pb2 import TaskStatus
from kiorga.datamodel.final_report_pb2 import FinalStatus

# === Logging-Konfiguration ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# === Globale Clients ===
# Initialisiert den Firestore-Client für Datenbank-Interaktionen
db = firestore.Client()
# Client zum Senden von Nachrichten an Google Cloud Pub/Sub
publisher = pubsub_v1.PublisherClient()
# Holt die Projekt-ID aus der Umgebung
PROJECT_ID = os.getenv("GCP_PROJECT")


# Initialisiert die Web-Anwendung
app = Flask(__name__)

@app.route("/", methods=["POST"])
def index():
    """
    Empfängt eine Aufgabe vom LDA über eine Pub/Sub-Nachricht.
    """
    envelope = request.get_json()    
    if not envelope:
        msg = "no Pub/Sub message received"
        logging.error(msg)
        return f"Bad Request: {msg}", 400
    if not isinstance(envelope, dict) or "message" not in envelope:
        msg = "invalid Pub/Sub message format"
        logging.error(msg)
        return f"Bad Request: {msg}", 400
    
    pubsub_message = envelope["message"]
    task = task_pb2.Task()

    if isinstance(pubsub_message, dict) and "data" in pubsub_message:
        try:
            # Task-Objekt aus der Nachricht parsen
            data_bytes = base64.b64decode(pubsub_message["data"])
            json_string_received = data_bytes.decode('utf-8')
            json_format.Parse(json_string_received, task)
            logging.info(f"SDA-BE received task: id={task.task_id}, title='{task.title}'")

            # IDEMPOTENZ-PRÜFUNG: Existiert bereits ein Abschlussbericht für diesen Task?
            reports_ref = db.collection("final_reports")
            # Firestore speichert die Felder in camelCase, daher "taskId" in der Abfrage
            query = reports_ref.where("taskId", "==", task.task_id).limit(1)
            existing_reports = list(query.stream())

            if existing_reports:
                logging.warning(f"Task {task.task_id} wurde bereits abgeschlossen (Report {existing_reports[0].id} existiert). Breche die Verarbeitung ab.")
                return "", 204 # Nachricht bestätigen, um erneute Zustellung zu verhindern

            # Task-Status auf IN_PROGRESS setzen
            task_doc_ref = db.collection("tasks").document(task.task_id)
            task_doc_ref.update({"status": TaskStatus.TASK_STATUS_IN_PROGRESS})
            logging.info(f"Task {task.task_id} status updated to IN_PROGRESS in Firestore.")

            # === EIGENTLICHE ARBEIT (HIER SIMULIERT) ===
            logging.info(f"Starting work on task {task.task_id}...")
            time.sleep(2) # Simuliert eine Arbeitsdauer von 2 Sekunden
            logging.info(f"Work on task {task.task_id} finished.")
            # ============================================

            # ABSCHLUSSBERICHT ERSTELLEN
            report_id = str(uuid.uuid4())
            final_report = final_report_pb2.FinalReport(
                report_id=report_id,
                task_id=task.task_id,
                executing_agent_id="agent-sda-be",
                final_status=FinalStatus.FINAL_STATUS_SUCCESS,
                summary="SDA-BE has successfully completed the simulated task.",
            )
            now = Timestamp()
            now.GetCurrentTime()
            final_report.completion_timestamp.CopyFrom(now)

            # WICHTIGE REIHENFOLGE FÜR IDEMPOTENZ:
            # 1. Bericht in Firestore speichern (als "Lock")
            # 2. Nachricht an Pub/Sub senden
            # 3. Task-Status in Firestore aktualisieren

            # 1. Bericht in Firestore speichern
            report_dict = json_format.MessageToDict(final_report)
            db.collection("final_reports").document(report_id).set(report_dict)
            logging.info(f"FinalReport {report_id} for task {task.task_id} saved to Firestore.")

            # 2. Nachricht an Pub/Sub senden
            # Wir verwenden den JSON-String, der aus dem Dict erstellt wird, um Konsistenz zu gewährleisten
            report_json_string = json.dumps(report_dict)
            report_bytes = report_json_string.encode('utf-8')
            topic_path = publisher.topic_path(PROJECT_ID, "final_reports")
            future = publisher.publish(topic_path, data=report_bytes)
            future.result() # Warten auf erfolgreichen Versand
            logging.info(f"Published FinalReport {report_id} for task {task.task_id} to Pub/Sub.")

            # 3. Task-Status aktualisieren
            task_doc_ref.update({"status": TaskStatus.TASK_STATUS_COMPLETED})
            logging.info(f"Task {task.task_id} status updated to COMPLETED.")

        except Exception as e:
            logging.error(f"Error processing Pub/Sub message: {e}", exc_info=True)
            # Task-Status auf FAILED setzen, um manuelle Inspektion zu ermöglichen
            if 'task' in locals() and task.task_id:
                try:
                    task_doc_ref = db.collection("tasks").document(task.task_id)
                    task_doc_ref.update({"status": TaskStatus.TASK_STATUS_FAILED})
                    logging.warning(f"Task {task.task_id} status updated to FAILED due to processing error.")
                except Exception as update_e:
                    logging.error(f"Could not even update task status to FAILED: {update_e}")
            
            # Wir geben 500 zurück, damit Pub/Sub die Nachricht erneut versucht (bis zur DLQ-Grenze)
            return "Internal Server Error: Could not process message", 500

    return "", 204

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
