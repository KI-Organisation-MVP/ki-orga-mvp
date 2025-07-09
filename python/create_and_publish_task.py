import uuid
import os
import logging
from dotenv import load_dotenv
from kiorga.datamodel import task_pb2
# Wir importieren die korrekten Enums
from kiorga.utils.pubsub_helpers import publish_proto_message_as_json
from kiorga.utils.validation import validate_task
from kiorga.datamodel.task_pb2 import TaskStatus, TaskPriority
from google.protobuf.timestamp_pb2 import Timestamp
from google.cloud import pubsub_v1

# Lädt die Umgebungsvariablen aus der .env-Datei im Root-Verzeichnis
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# Sauberes Logging konfigurieren
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Konfiguration ---
PROJECT_ID = os.getenv("GCP_PROJECT")
ASSIGN_TOPIC_ID = os.getenv("TOPIC_LDA_TASKS") # Topic für die Zuweisung von Aufgaben

if not all([PROJECT_ID, ASSIGN_TOPIC_ID]):
    raise EnvironmentError("Fehlende Umgebungsvariablen: GCP_PROJECT, TASK_ASSIGNMENTS_TOPIC müssen gesetzt sein.")
# ---------------------

def create_and_publish_task():
    """Erstellt ein neues Task-Objekt und veröffentlicht es direkt in Pub/Sub.
    Rückgabe: (success: bool, error_code: str|None, error_message: str|None)
    """
    
    # 1. Task-Objekt erstellen und mit Testdaten befüllen
    task = task_pb2.Task()
    task.task_id = str(uuid.uuid4())  # Eindeutige ID generieren
    task.title = "Erster Test nach der Umstellung von flask auf FastAPI"
    task.description = "Dieser Task wurde direkt aus einem Python-Skript veröffentlicht, um Encoding-Fehler zu vermeiden."
    
    # KORREKTER STATUS-WERT setzen
    task.status = TaskStatus.TASK_STATUS_PENDING
    
    task.priority = TaskPriority.TASK_PRIORITY_URGENT
    task.creator_agent_id = "system-test-script"
    
    # Aktuellen Zeitstempel setzen
    now = Timestamp()
    now.GetCurrentTime()
    task.created_at.CopyFrom(now)

    # Anwendung der Validierung vor der Serialisierung:
    validation_errors = validate_task(task)
    if validation_errors:
        error_msg = f"Fehlerhafte Felder: {validation_errors}"
        print(error_msg)
        return (False, "VALIDATION_ERROR", error_msg)

    logging.info(f"Erstelle Task mit ID: {task.task_id}")

    # 3. Nachricht mit Fehlerbehandlung an Pub/Sub veröffentlichen
    try:
        publisher = pubsub_v1.PublisherClient()
        publish_proto_message_as_json(
            publisher=publisher,
            project_id=PROJECT_ID,
            topic_id=ASSIGN_TOPIC_ID,
            proto_message=task
        )
        return (True, None, None)
    except IOError as e:
        logging.error(f"Fehler bei der Pub/Sub-API während des Veröffentlichens: {e}")
        return (False, "PUBSUB_API_ERROR", str(e))
    except Exception as e:
        logging.error(f"Ein unerwarteter Fehler ist aufgetreten: {e}")
        return (False, "UNEXPECTED_ERROR", str(e))

if __name__ == "__main__":
    # Hauptausführung: Task erstellen und veröffentlichen
    success, error_code, error_message = create_and_publish_task()
    if success:
        print("\nSkript erfolgreich ausgeführt. Nachricht wurde an Pub/Sub gesendet.")
    else:
        print(f"\nFehler bei der Ausführung des Skripts [{error_code}]: {error_message}")