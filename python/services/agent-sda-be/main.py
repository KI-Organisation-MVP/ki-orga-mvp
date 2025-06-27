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
            # --- KORREKTUR: Der LDA sendet JSON, nicht binäres Protobuf ---
            data_bytes = base64.b64decode(pubsub_message["data"])
            json_string_received = data_bytes.decode('utf-8')
            json_format.Parse(json_string_received, task)
            # -------------------------------------------------------------
            logging.info(f"SDA-BE received task: id={task.taskId}, title='{task.title}'")

            # Der SDA-BE erstellt den Task nicht neu, sondern aktualisiert seinen Status.
            doc_ref = db.collection("tasks").document(task.taskId)
            doc_ref.update({"status": TaskStatus.TASK_STATUS_IN_PROGRESS})            
            logging.info(f"Task {task.taskId} status updated to IN_PROGRESS in Firestore.")

            # === EIGENTLICHE ARBEIT (HIER SIMULIERT) ===
            # TODO: Hier sollte die eigentliche Logik zur Bearbeitung der Aufgabe implementiert werden.
            logging.info(f"Starting work on task {task.taskId}...")
            time.sleep(2) # Simuliert eine Arbeitsdauer von 2 Sekunden
            logging.info(f"Work on task {task.taskId} finished.")
            # ============================================

            # NEUE LOGIK: Abschlussbericht erstellen und senden
            # ------------------------------------------------
            final_report = final_report_pb2.FinalReport(
                reportId           = str(uuid.uuid4()),
                taskId             = task.taskId,
                executingAgentId  = "agent-sda-be",
                finalStatus        = FinalStatus.FINAL_STATUS_SUCCESS,
                summary             = "SDA-BE has successfully completed the simulated task.",
            )

            # Zeitstempel für den Abschluss setzen
            now = Timestamp()
            now.GetCurrentTime()
            final_report.completionTimestamp.CopyFrom(now)
            
            # Den Bericht als Byte-String serialisieren
            report_bytes = final_report.SerializeToString()

            # Den Bericht auf dem final_reports-Topic veröffentlichen
            topic_path = publisher.topic_path(PROJECT_ID, "final_reports")
            future = publisher.publish(topic_path, data=report_bytes)
            future.result() # Wartet auf den erfolgreichen Versand

            logging.info(f"Published FinalReport {final_report.reportId} for task {task.taskId}")
            # ------------------------------------------------

        except Exception as e:
            logging.error(f"Error processing Pub/Sub message: {e}", exc_info=True)
            return "Bad Request: Could not process message", 400

    return "", 204

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))