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
from dotenv import load_dotenv


# Lädt die Umgebungsvariablen aus der .env-Datei im Root-Verzeichnis
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

from kiorga.datamodel import task_pb2
from kiorga.datamodel import final_report_pb2
from kiorga.datamodel.task_pb2 import TaskStatus
from kiorga.datamodel.final_report_pb2 import FinalStatus

# === Logging-Konfiguration ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# === Globale Clients und Konstanten ===
db = firestore.Client()
publisher = pubsub_v1.PublisherClient()

# Lädt die Konfiguration aus Umgebungsvariablen.
PROJECT_ID = os.getenv("GCP_PROJECT")
AGENT_ID = os.getenv("AGENT_ID_SDA_BE")  # Agent SDA_BE, der die Aufgaben zugewiesen bekommt
TOPIC_REPORTS = os.getenv("TOPIC_REPORTS")  # Topic für Abschlussberichte

# Stellt sicher, dass alle notwendigen Umgebungsvariablen gesetzt sind.
if not all([PROJECT_ID, AGENT_ID, TOPIC_REPORTS]):
    raise EnvironmentError("Fehlende Umgebungsvariablen: GCP_PROJECT, AGENT_ID, REPORTS_TOPIC müssen gesetzt sein.")

# Initialisiert die Web-Anwendung
app = Flask(__name__)


def parse_task_from_request(envelope: dict) -> task_pb2.Task:
    """
    Extrahiert die Nachricht aus dem Pub/Sub-Envelope, dekodiert sie (Base64)
    und parst den resultierenden JSON-String in ein Task-Protobuf-Objekt.
    """
    if not envelope:
        raise ValueError("no Pub/Sub message received")
    if not isinstance(envelope, dict) or "message" not in envelope:
        raise ValueError("invalid Pub/Sub message format")

    pubsub_message = envelope["message"]
    if not isinstance(pubsub_message, dict) or "data" not in pubsub_message:
        raise ValueError("Pub/Sub message missing 'data' field")

    try:
        data_bytes = base64.b64decode(pubsub_message["data"])
        json_string_received = data_bytes.decode('utf-8')
        task = task_pb2.Task()
        json_format.Parse(json_string_received, task)
        logging.info(f"SDA-BE received task: id={task.task_id}, title='{task.title}'")
        return task
    except Exception as e:
        logging.error(f"Fehler beim Parsen des Tasks: {e}", exc_info=True)
        raise ValueError("could not parse task from message") from e


def check_idempotency(task_id: str) -> bool:
    """
    Stellt die Idempotenz sicher, indem geprüft wird, ob für einen gegebenen Task
    bereits ein Abschlussbericht in Firestore existiert.

    Returns:
        bool: True, wenn bereits ein Bericht existiert (Verarbeitung abbrechen),
              False, wenn kein Bericht existiert (Verarbeitung fortsetzen).
    """
    reports_ref = db.collection("final_reports")
    # Firestore speichert Protobuf-JSON-Felder in camelCase.
    query = reports_ref.where("taskId", "==", task_id).limit(1)
    existing_reports = list(query.stream())
    if existing_reports:
        logging.warning(f"Task {task_id} wurde bereits abgeschlossen (Report {existing_reports[0].id} existiert). Breche die Verarbeitung ab.")
        return True
    return False


def update_task_status(task_id: str, status: TaskStatus):
    """
    Aktualisiert das 'status'-Feld eines Task-Dokuments in Firestore.
    Fehler werden geloggt, aber nicht weitergeworfen, um den Haupt-Workflow
    (insbesondere das Setzen des FAILED-Status) nicht zu gefährden.
    """
    try:
        task_doc_ref = db.collection("tasks").document(task_id)
        task_doc_ref.update({"status": status})
        logging.info(f"Task {task_id} status updated to {TaskStatus.Name(status)} in Firestore.")
    except Exception as e:
        logging.error(f"Konnte Task-Status für {task_id} nicht auf {TaskStatus.Name(status)} aktualisieren: {e}", exc_info=True)


def perform_simulated_work(task_id: str):
    """
    Simuliert die eigentliche "Arbeit", die dieser Agent ausführt.
    In einem echten Szenario würde hier die Geschäftslogik stehen.
    """
    logging.info(f"Starting work on task {task_id}...")
    time.sleep(2)  # Simuliert eine Arbeitsdauer von 2 Sekunden
    logging.info(f"Work on task {task_id} finished.")


def create_and_publish_final_report(task_id: str):
    """
    Erstellt einen Abschlussbericht, speichert ihn in Firestore und veröffentlicht
    ihn anschließend in einem Pub/Sub-Topic.

    Die Reihenfolge (zuerst Firestore, dann Pub/Sub) ist wichtig, um zu
    verhindern, dass eine Nachricht mehrfach verarbeitet wird, falls der
    Pub/Sub-Versand fehlschlägt und wiederholt wird.
    """
    report_id = str(uuid.uuid4())
    now = Timestamp()
    now.GetCurrentTime()

    final_report = final_report_pb2.FinalReport(
        report_id=report_id,
        task_id=task_id,
        executing_agent_id=AGENT_ID,
        final_status=FinalStatus.FINAL_STATUS_SUCCESS,
        summary="SDA-BE has successfully completed the simulated task.",
        completion_timestamp=now
    )

    try:
        # Schritt 1: Bericht in Firestore speichern. Dies dient als "Lock",
        # um bei Wiederholungen die Idempotenzprüfung in `check_idempotency` auszulösen.
        report_dict = json_format.MessageToDict(final_report)
        db.collection("final_reports").document(report_id).set(report_dict)
        logging.info(f"FinalReport {report_id} for task {task_id} saved to Firestore.")

        # Schritt 2: Nachricht an Pub/Sub senden, um nachgelagerte Prozesse zu informieren.
        report_json_string = json.dumps(report_dict)
        report_bytes = report_json_string.encode('utf-8')
        topic_path = publisher.topic_path(PROJECT_ID, TOPIC_REPORTS)
        future = publisher.publish(topic_path, data=report_bytes)
        future.result(timeout=30)  # Warten auf erfolgreichen Versand
        logging.info(f"Published FinalReport {report_id} for task {task_id} to Pub/Sub.")
    except Exception as e:
        logging.error(f"Fehler beim Speichern oder Veröffentlichen des Berichts für Task {task_id}: {e}", exc_info=True)
        raise IOError("could not persist or publish final report") from e


@app.route("/", methods=["POST"])
def index():
    """
    Haupt-Endpunkt, der die Task-Verarbeitung orchestriert.

    Workflow:
    1. Task aus der eingehenden Pub/Sub-Nachricht parsen.
    2. Prüfen, ob der Task bereits bearbeitet wurde (Idempotenz).
    3. Task-Status auf "IN_PROGRESS" setzen.
    4. Die eigentliche (simulierte) Arbeit ausführen.
    5. Einen Abschlussbericht erstellen und veröffentlichen.
    6. Task-Status auf "COMPLETED" setzen.
    """
    task = None
    try:
        envelope = request.get_json()
        # Schritt 1: Task aus der Nachricht extrahieren und validieren.
        task = parse_task_from_request(envelope)

        # Schritt 2: Idempotenzprüfung. Verhindert doppelte Ausführung.
        if check_idempotency(task.task_id):
            return "", 204  # Task wurde bereits verarbeitet, Nachricht bestätigen.

        # Schritt 3: Status auf IN_PROGRESS setzen, um Transparenz zu schaffen.
        update_task_status(task.task_id, TaskStatus.TASK_STATUS_IN_PROGRESS)

        # Schritt 4: Die eigentliche Arbeit wird ausgeführt.
        perform_simulated_work(task.task_id)

        # Schritt 5: Abschlussbericht erstellen und für andere Systeme bereitstellen.
        create_and_publish_final_report(task.task_id)

        # Schritt 6: Finalen Status in Firestore setzen.
        update_task_status(task.task_id, TaskStatus.TASK_STATUS_COMPLETED)

        # Erfolgreiche Verarbeitung mit 204 No Content an Pub/Sub quittieren.
        return "", 204

    except ValueError as e:
        # Fehler beim Parsen der Nachricht. Führt zu einem 400 Bad Request.
        # Die Nachricht wird von Pub/Sub nicht erneut zugestellt.
        return f"Bad Request: {e}", 400
    except Exception as e:
        # Alle anderen Fehler (z.B. bei Firestore, Pub/Sub, Geschäftslogik).
        logging.error(f"Error processing message for task {getattr(task, 'task_id', 'N/A')}: {e}", exc_info=True)
        
        # Im Fehlerfall wird versucht, den Task-Status auf FAILED zu setzen.
        if task and task.task_id:
            update_task_status(task.task_id, TaskStatus.TASK_STATUS_FAILED)
        
        # Ein 500-Fehler signalisiert Pub/Sub, dass die Verarbeitung fehlgeschlagen ist.
        # Pub/Sub wird versuchen, die Nachricht erneut zuzustellen.
        return "Internal Server Error: Could not process message", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
