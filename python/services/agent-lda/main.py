import os
import base64
import json
import logging
from flask import Flask, request

# Importiert die generierte Python-Klasse für unser Task-Objekt
from kiorga.datamodel import task_pb2

# === Logging-Konfiguration ===
# Konfiguriert das Standard-Logging, um von Google Cloud Logging erfasst zu werden.
# Indem wir keinen Handler explizit definieren, nutzt es den Standard-Stream,
# den Cloud Run automatisch abfängt und formatiert.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Initialisiert die Web-Anwendung
app = Flask(__name__)

@app.route("/", methods=["POST"])
def index():
    """
    Empfängt, dekodiert und verarbeitet eine Pub/Sub-Nachricht, die ein Task-Objekt enthält.
    """
    # Überprüfen, ob die Anfrage einen gültigen JSON-Body hat
    envelope = request.get_json()
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
    task = task_pb2.Task() # Erstellt eine leere Instanz unseres Task-Objekts
    
    # In einer echten Nachricht sind die Daten base64-kodiert.
    # Wir werden sie später hier dekodieren und verarbeiten.
    if isinstance(pubsub_message, dict) and "data" in pubsub_message:
        try:
            # Dekodiert die Base64-Daten in einen Byte-String
            data_bytes = base64.b64decode(pubsub_message["data"])
            
            # Wandelt den Byte-String in unser strukturiertes Task-Objekt um
            task.FromString(data_bytes)
            
            logging.info(f"Successfully parsed Task object: id={task.task_id}, title='{task.title}'")

        except Exception as e:
            logging.error(f"Error parsing Task object from Pub/Sub message: {e}", exc_info=True)
            return "Bad Request: Could not parse Task object", 400

    # NÄCHSTER SCHRITT (P3.5): Hier kommt die Logik, um das 'task'-Objekt
    # in Firestore zu speichern.

    # Eine leere "204 No Content"-Antwort signalisiert Pub/Sub,
    # dass die Nachricht erfolgreich empfangen wurde und nicht erneut gesendet werden muss.
    return "", 204

if __name__ == "__main__":
    # Startet den Server. Cloud Run setzt automatisch den PORT.
    # Lokal würde er auf Port 8080 laufen.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))