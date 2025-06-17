import os
import base64
import json
import logging

from flask import Flask, request

# Importiert die generierte Python-Klasse für unser Task-Objekt
from kiorga.datamodel import task_pb2
from google.cloud import firestore

# === Logging-Konfiguration ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# === Globale Clients ===
# Initialisiert den Firestore-Client für Datenbank-Interaktionen
db = firestore.Client()

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
            data_bytes = base64.b64decode(pubsub_message["data"])
            task.FromString(data_bytes)
            logging.info(f"SDA-BE received task: id={task.task_id}, title='{task.title}'")

            # Der SDA-BE erstellt den Task nicht neu, sondern aktualisiert seinen Status.
            doc_ref = db.collection("tasks").document(task.task_id)
            # Wir aktualisieren das 'status'-Feld auf IN_PROGRESS.
            # Wir importieren dafür die Enum-Werte aus der pb2-Datei.
            from kiorga.datamodel.task_pb2 import TaskStatus
            doc_ref.update({"status": TaskStatus.TASK_STATUS_IN_PROGRESS})
            
            logging.info(f"Task {task.task_id} status updated to IN_PROGRESS in Firestore.")


        except Exception as e:
            logging.error(f"Error processing Pub/Sub message: {e}", exc_info=True)
            return "Bad Request: Could not process message", 400

    return "", 204

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))