# Force rebuild
import os
import base64
import json
import logging
from flask import Flask, request

from google.cloud import firestore
from google.protobuf import json_format
# Importiert die Protobuf-Definition für das Task-Objekt.
from kiorga.datamodel import task_pb2

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

# Initialisiert die Web-Anwendung
app = Flask(__name__)

@app.route("/", methods=["POST"])
def index():
    """
    Empfängt, dekodiert und verarbeitet eine Pub/Sub-Nachricht, die ein Task-Objekt enthält.
    """
    # Überprüfen, ob die Anfrage einen gültigen JSON-Body hat
    envelope = request.get_json()

    logging.info(f"Full request envelope received: {json.dumps(envelope, indent=2)}")

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
            logging.info(f"PS pubsub_message: {pubsub_message['data']}")
            # Dekodiert die Base64-Daten in einen Byte-String
            try:
                data_bytes = base64.b64decode(pubsub_message["data"])
            except Exception as e:
                logging.error(f"Base64-Dekodierung fehlgeschlagen: {e}", exc_info=True)
                return "Bad Request: base64 decode error", 400

            logging.info(f"Empfangene Nachrichten-DNA (Hex): {data_bytes.hex()}")

            # Wandelt den Byte-String in unser strukturiertes Task-Objekt um
            try:
                task.FromString(data_bytes)
            except Exception as e:
                logging.error(f"Protobuf-Deserialisierung fehlgeschlagen: {e}", exc_info=True)
                return "Bad Request: protobuf parse error", 422

            logging.info(f"Successfully parsed Task object: id={task.task_id}, title='{task.title}'")
            
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
                task_dict = json.loads(json_format.MessageToJson(task))
                doc_ref = db.collection("tasks").document(task.task_id)
                doc_ref.set(task_dict)
                logging.info(f"Task {task.task_id} successfully saved to Firestore.")
            except Exception as e:
                logging.error(f"Fehler beim Speichern in Firestore: {e}", exc_info=True)
                return "Internal Server Error: Firestore write error", 500

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
    valid_status = [
        getattr(task, "TASK_STATUS_PENDING", None),
        getattr(task, "TASK_STATUS_COMPLETED", None),
        getattr(task, "TASK_STATUS_IN_PROGRESS", None),
        getattr(task, "TASK_STATUS_FAILED", None),
    ]
    if task.status not in valid_status:
        errors.append("status ist ungültig")
    valid_priority = [
        getattr(task, "TASK_PRIORITY_LOW", None),
        getattr(task, "TASK_PRIORITY_MEDIUM", None),
        getattr(task, "TASK_PRIORITY_HIGH", None),
        getattr(task, "TASK_PRIORITY_URGENT", None),
        getattr(task, "TASK_PRIORITY_OPTIONAL", None),
    ]
    if task.priority not in valid_priority:
        errors.append("priority ist ungültig")
    if not task.creator_agent_id:
        errors.append("creator_agent_id fehlt")
    if not task.created_at or getattr(task.created_at, "seconds", 0) == 0:
        errors.append("created_at fehlt oder ist ungültig")
    return errors

if __name__ == "__main__":
    # Startet den Server. Cloud Run setzt automatisch den PORT.
    # Lokal würde er auf Port 8080 laufen.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))