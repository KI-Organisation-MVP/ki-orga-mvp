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