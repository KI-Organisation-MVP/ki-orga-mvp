import base64
import uuid
from kiorga.datamodel import task_pb2
from kiorga.datamodel.task_pb2 import TaskStatus, TaskPriority
from google.protobuf.timestamp_pb2 import Timestamp

# Erstelle eine Instanz des Task-Objekts
task = task_pb2.Task()

# Fülle das Objekt mit Daten für unseren ersten Auftrag
task.task_id = str(uuid.uuid4())
task.title = "Initiales MVP Setup für neuen Kunden 'Innovate GmbH'"
task.description = "Erstelle die komplette Grundinfrastruktur für einen neuen Kunden, basierend auf dem Standard-MVP-Prozess."
task.status = TaskStatus.TASK_STATUS_PENDING
task.priority = TaskPriority.TASK_PRIORITY_HIGH
task.creator_agent_id = "user-philipp" # Manuell ausgelöst

# Setze das Erstellungsdatum auf jetzt
now = Timestamp()
task.created_at.GetCurrentTime()

# Beispiel für eine einfache Validierungsfunktion
def validate_task(task):
    errors = []
    if not task.task_id:
        errors.append("task_id fehlt")
    if not task.title or len(task.title.strip()) == 0:
        errors.append("title fehlt oder ist leer")
    if not task.description or len(task.description.strip()) == 0:
        errors.append("description fehlt oder ist leer")
    if task.status not in [TaskStatus.TASK_STATUS_PENDING, TaskStatus.TASK_STATUS_DONE]:
        errors.append("status ist ungültig")
    if task.priority not in [TaskPriority.TASK_PRIORITY_LOW, TaskPriority.TASK_PRIORITY_MEDIUM, TaskPriority.TASK_PRIORITY_HIGH]:
        errors.append("priority ist ungültig")
    if not task.creator_agent_id:
        errors.append("creator_agent_id fehlt")
    # created_at kann z.B. auf 0 geprüft werden
    if not task.created_at or task.created_at.seconds == 0:
        errors.append("created_at fehlt oder ist ungültig")
    return errors

# Anwendung vor der Serialisierung:
validation_errors = validate_task(task)
if validation_errors:
    print("Fehlerhafte Felder:", validation_errors)
    exit(1)

try:
    # Serialisiere das Objekt in einen binären Byte-String
    serialized_task = task.SerializeToString()
    print("--- Eindeutige DNA der Nachricht (ohne HEX) ---")
    print(serialized_task)
    print("----------------------------------------")
    # Kodiere den Byte-String in Base64 für den Versand via gcloud Pub/Sub
    base64_encoded_task = base64.b64encode(serialized_task).decode('utf-8')
    # --- NEUE DIAGNOSE-AUSGABE ---
    print("--- Eindeutige DNA der Nachricht (Hex) ---")
    print(serialized_task.hex())
    print("----------------------------------------")

    # Gib den finalen String aus
    print("--- Dein Base64-kodierter Task ---")
    print(base64_encoded_task)
    print("---------------------------------")
except Exception as e:
    print(f"Fehler beim Erstellen oder Kodieren des Tasks: {e}")