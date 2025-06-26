# Force rebuild
import os
import base64
import json
import logging
from flask import Flask, request
from google.cloud import firestore
from google.cloud import pubsub_v1
from google.protobuf import json_format
from google.protobuf.timestamp_pb2 import Timestamp
# Importiert die Protobuf-Definition für das Task-Objekt.
from kiorga.datamodel import task_pb2

# TODO: Erwägen Sie die Verwendung von strukturiertem Logging (z.B. durch google.cloud.logging.handlers.CloudLoggingHandler oder eine Bibliothek wie python-json-logger), um Logs direkt in Cloud Logging zu senden und sie dort besser abfragen und analysieren zu können. Für eine kleine Anwendung ist basicConfig oft ausreichend, aber für komplexere Szenarien ist strukturiertes Logging vorteilhaft.
# TODO: Überlegen Sie, ob Sie eine zentrale Logging-Konfiguration in einer separaten Datei oder einem Modul auslagern möchten, um die Wiederverwendbarkeit und Wartbarkeit zu verbessern.
# TODO: In einer produktiven Umgebung sollten Sie auch Fehlerbehandlung und Wiederholungslogik für die Firestore- und Pub/Sub-Operationen implementieren, um Robustheit zu gewährleisten.
# TODO: Hardcodierte Agenten-IDs (wie "agent-sda-be") sollten in einer Konfigurationsdatei oder Umgebungsvariablen gespeichert werden, um Flexibilität und Anpassbarkeit zu ermöglichen.
# TODO: Hardcodierte Agenten-ID: Problem: Die assignedToAgentId wird in Firestore hart auf "agent-sda-be" gesetzt.
#       Vorschlag: Während dies für das MVP-Szenario in Ordnung sein mag, könnte in einem komplexeren System der LDA Logik enthalten, um den am besten geeigneten Agenten basierend auf Task-Typ, Auslastung oder anderen Kriterien auszuwählen. Dies ist eher ein Design-Hinweis als ein direkter Code-Fehler, aber es ist gut, dies im Hinterkopf zu behalten.

# === Logging-Konfiguration ===
# Konfiguriert das Standard-Logging, um von Google Cloud Logging erfasst zu werden.
# Indem wir keinen Handler explizit definieren, nutzt es den Standard-Stream,
# den Cloud Run automatisch abfängt und formatiert.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# === Globale Clients ===
# Initialisiert den Firestore-Client.
# Die Authentifizierung erfolgt automatisch über die Umgebung, in der der Code läuft (z.B. Cloud Run).
db = firestore.Client()
publisher = pubsub_v1.PublisherClient()
PROJECT_ID = os.environ.get("GCP_PROJECT", "ki-orga-mvp")

# Initialisiert die Web-Anwendung
app = Flask(__name__)

@app.route("/", methods=["POST"])
def index():
    """
    Empfängt, dekodiert und verarbeitet eine Pub/Sub-Nachricht, die ein Task-Objekt enthält.
    """
    # Überprüfen, ob die Anfrage einen gültigen JSON-Body hat
    envelope = request.get_json()
    # logging.info(f"Full request envelope received: {json.dumps(envelope, indent=2)}")

    if not envelope:
        msg = "no Pub/Sub message received"
        logging.error(msg)
        return f"Bad Request: {msg}", 400

    # Überprüfen, ob die Nachricht das erwartete Pub/Sub-Format hat
    if not isinstance(envelope, dict) or "message" not in envelope:
        msg = "invalid Pub/Sub message format"
        logging.error(msg)
        return f"Bad Request: {msg}", 400

    pubsub_message = envelope["message"]
    task = task_pb2.Task()
    
    # In einer echten Nachricht sind die Daten base64-kodiert.
    if isinstance(pubsub_message, dict) and "data" in pubsub_message:
        try:
            # Dekodiert die Base64-Daten in einen Byte-String
            try:
                data_bytes = base64.b64decode(pubsub_message["data"])
            except Exception as e:
                logging.error(f"Base64-Dekodierung fehlgeschlagen: {e}", exc_info=True)
                return "Bad Request: base64 decode error", 400

            logging.info(f"Empfangene Nachrichten-DNA (Hex): {data_bytes.hex()}")
            # ... und wandeln sie zurück in den JSON-String.
            json_string_received = data_bytes.decode('utf-8')
            logging.info(f"Empfangene JSON-Daten: {json_string_received}")

            # Wandelt den Byte-String in unser strukturiertes Task-Objekt um
            try:
                # task.FromString(data_bytes)
                # --- NEUE DESERIALISIERUNG ---
                # Wir parsen den JSON-String in unser leeres Task-Objekt.
                json_format.Parse(json_string_received, task)
            
            except Exception as e:
                logging.error(f"Protobuf-Deserialisierung fehlgeschlagen: {e}", exc_info=True)
                return "Bad Request: protobuf parse error", 422

            logging.info(f"Successfully parsed Task object from JSON: id={task.task_id}, title='{task.title}'")

            # Validiert das Task-Objekt
            validation_errors = validate_task(task)
            if validation_errors:
                error_msg = f"Fehlerhafte Felder: {validation_errors}"
                logging.error(error_msg)
                return f"Bad Request: {error_msg}", 422
            logging.info("Task-Objekt erfolgreich validiert.")
            # Loggt die wichtigsten Felder des Task-Objekts
            logging.info(f"Task-Details: ID={task.task_id}, Title='{task.title}', Status={task.status}, Priority={task.priority}, Creator='{task.creator_agent_id}'")
            
            
            # Task in Firestore speichern
            try:
                task_dict = json_format.MessageToDict(task)
                doc_ref = db.collection("tasks").document(task.task_id)
                doc_ref.set(task_dict)
                logging.info(f"Task {task.task_id} successfully saved to Firestore.")
            except Exception as e:
                logging.error(f"Fehler beim Speichern in Firestore: {e}", exc_info=True)
                return "Internal Server Error: Firestore write error", 500
            

            # +++ NEUE DELEGATIONS-LOGIK +++
            # -------------------------------
            # Annahme: Der LDA delegiert diesen Task direkt an den SDA-BE
            if task.task_id: # Nur delegieren, wenn eine gültige Task-ID vorhanden ist
                logging.info(f"Delegating task {task.task_id} to SDA-BE...")
                
                # Wir senden den gleichen Task weiter. Die Nachricht ist der JSON-String.
                data_to_send = json_string_received.encode('utf-8')
                
                # Wir veröffentlichen auf dem Topic für den Backend-Agenten
                topic_path = publisher.topic_path(PROJECT_ID, "sda_be_tasks")
                future = publisher.publish(topic_path, data=data_to_send)
                
                message_id = future.result(timeout=30)
                logging.info(f"Successfully delegated task to 'sda_be_tasks' topic. Message ID: {message_id}")
            # -------------------------------

            # +++ FINALE LOGIK: TASK-STATUS AKTUALISIEREN +++
            # --------------------------------------------------
            # Nachdem die Delegation erfolgreich war, aktualisieren wir das Dokument in Firestore.
            update_data = {
                "status": task_pb2.TaskStatus.TASK_STATUS_IN_PROGRESS,
                "assignedToAgentId": "agent-sda-be", # Wichtig: Firestore nutzt camelCase für Feldnamen aus JSON
                "updated_at": firestore.SERVER_TIMESTAMP # Setzt den Zeitstempel auf die aktuelle Serverzeit   
            }
            doc_ref.update(update_data)
            logging.info(f"Task {task.task_id} status updated to IN_PROGRESS and assigned to sda-be.")
            # --------------------------------------------------

        except Exception as e:
            logging.error(f"Unerwarteter Fehler beim Verarbeiten der Pub/Sub-Nachricht: {e}", exc_info=True)
            return "Internal Server Error: unexpected error", 500

    else:
        logging.error("Pub/Sub message missing 'data' field")
        return "Bad Request: missing data field", 400

    # Eine leere "204 No Content"-Antwort signalisiert Pub/Sub,
    # dass die Nachricht erfolgreich empfangen wurde und nicht erneut gesendet werden muss.
    return "", 204

def validate_task(task):
    """
    Prüft, ob alle Pflichtfelder im Task-Objekt korrekt gesetzt sind.
    Gibt eine Liste von Fehlern zurück, falls vorhanden.
    """
    errors = []
    if not task.task_id:
        errors.append("task_id fehlt")
    if not task.title or len(task.title.strip()) == 0:
        errors.append("title fehlt oder ist leer")
    if not task.description or len(task.description.strip()) == 0:
        errors.append("description fehlt oder ist leer")
    # Beispielhafte Status- und Prioritätswerte, ggf. anpassen:

    # Korrekte Überprüfung der Status- und Prioritätswerte
    valid_status_values = [
        task_pb2.TaskStatus.TASK_STATUS_UNSPECIFIED, # Standardwert, wenn nicht gesetzt
        task_pb2.TaskStatus.TASK_STATUS_PENDING,
        task_pb2.TaskStatus.TASK_STATUS_COMPLETED,
        task_pb2.TaskStatus.TASK_STATUS_IN_PROGRESS,
        task_pb2.TaskStatus.TASK_STATUS_FAILED,
    ]
    if task.status not in valid_status_values:
        errors.append(f"status ist ungültig: {task.status}")

    valid_priority_values = [
        task_pb2.TaskPriority.TASK_PRIORITY_UNSPECIFIED, # Standardwert, wenn nicht gesetzt
        task_pb2.TaskPriority.TASK_PRIORITY_LOW,
        task_pb2.TaskPriority.TASK_PRIORITY_MEDIUM,
        task_pb2.TaskPriority.TASK_PRIORITY_HIGH,
        task_pb2.TaskPriority.TASK_PRIORITY_URGENT,
        task_pb2.TaskPriority.TASK_PRIORITY_OPTIONAL,
    ]
    if task.priority not in valid_priority_values:
        errors.append(f"priority ist ungültig: {task.priority}")

    if not task.creator_agent_id:
        errors.append("creator_agent_id fehlt")
    if not task.created_at or getattr(task.created_at, "seconds", 0) == 0:
        errors.append("created_at fehlt oder ist ungültig")
    return errors

if __name__ == "__main__":
    # Startet den Server. Cloud Run setzt automatisch den PORT.
    # Lokal würde er auf Port 8080 laufen.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))