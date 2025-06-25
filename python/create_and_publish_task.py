import uuid
import os
import logging
from kiorga.datamodel import task_pb2
# Wir importieren die korrekten Enums
from kiorga.datamodel.task_pb2 import TaskStatus, TaskPriority
from google.protobuf.timestamp_pb2 import Timestamp
from google.cloud import pubsub_v1
from google.api_core import exceptions

# Sauberes Logging konfigurieren
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Konfiguration ---
PROJECT_ID = "ki-orga-mvp"  # GCP-Projekt-ID
TOPIC_ID = "task_assignments"  # Pub/Sub-Topic-Name
# ---------------------

def create_and_publish_task():
    """Erstellt ein neues Task-Objekt und veröffentlicht es direkt in Pub/Sub.
    Rückgabe: (success: bool, error_code: str|None, error_message: str|None)
    """
    
    # 1. Task-Objekt erstellen und mit Testdaten befüllen
    task = task_pb2.Task()
    task.task_id = str(uuid.uuid4())  # Eindeutige ID generieren
    task.title = "Finaler Test V2: Direkt-Publish eines neuen Auftrags"
    task.description = "Dieser Task wurde direkt aus einem Python-Skript veröffentlicht, um Encoding-Fehler zu vermeiden."
    
    # KORREKTER STATUS-WERT setzen
    task.status = TaskStatus.TASK_STATUS_PENDING
    
    task.priority = TaskPriority.TASK_PRIORITY_URGENT
    task.creator_agent_id = "system-test-script"
    
    # Aktuellen Zeitstempel setzen
    now = Timestamp()
    now.GetCurrentTime()
    task.created_at.CopyFrom(now)

    # Beispiel für eine einfache Validierungsfunktion
    def validate_task(task):
        """Prüft, ob alle Pflichtfelder im Task-Objekt korrekt gesetzt sind."""
        errors = []
        if not task.task_id:
            errors.append("task_id fehlt")
        if not task.title or len(task.title.strip()) == 0:
            errors.append("title fehlt oder ist leer")
        if not task.description or len(task.description.strip()) == 0:
            errors.append("description fehlt oder ist leer")
        if task.status not in [TaskStatus.TASK_STATUS_PENDING, TaskStatus.TASK_STATUS_COMPLETED, TaskStatus.TASK_STATUS_IN_PROGRESS, TaskStatus.TASK_STATUS_FAILED]:
            errors.append("status ist ungültig")
        if task.priority not in [TaskPriority.TASK_PRIORITY_LOW, TaskPriority.TASK_PRIORITY_MEDIUM, TaskPriority.TASK_PRIORITY_HIGH, TaskPriority.TASK_PRIORITY_URGENT, TaskPriority.TASK_PRIORITY_OPTIONAL]:
            errors.append("priority ist ungültig")
        if not task.creator_agent_id:
            errors.append("creator_agent_id fehlt")
        # created_at kann z.B. auf 0 geprüft werden
        if not task.created_at or task.created_at.seconds == 0:
            errors.append("created_at fehlt oder ist ungültig")
        return errors

    # Anwendung der Validierung vor der Serialisierung:
    validation_errors = validate_task(task)
    if validation_errors:
        error_msg = f"Fehlerhafte Felder: {validation_errors}"
        print(error_msg)
        return (False, "VALIDATION_ERROR", error_msg)

    # 2. Task in binäre Daten serialisieren (Protobuf)
    data_to_send = task.SerializeToString()
    logging.info(f"Erstelle Task mit ID: {task.task_id}")

    # 3. Nachricht mit Fehlerbehandlung an Pub/Sub veröffentlichen
    try:
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
        
        # Nachricht veröffentlichen (asynchron)
        future = publisher.publish(topic_path, data=data_to_send)
        
        # Auf das Ergebnis warten (max. 30 Sekunden)
        message_id = future.result(timeout=30)
        logging.info(f"Nachricht erfolgreich veröffentlicht mit Message ID: {message_id}")
        return (True, None, None)
    except exceptions.GoogleAPICallError as e:
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