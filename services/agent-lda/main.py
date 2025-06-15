import os
import base64
import json
import logging
from flask import Flask, request

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
    Empfängt und verarbeitet eine per HTTP-Push zugestellte Pub/Sub-Nachricht.
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
    
    # In einer echten Nachricht sind die Daten base64-kodiert.
    # Wir werden sie später hier dekodieren und verarbeiten.
    if isinstance(pubsub_message, dict) and "data" in pubsub_message:
        try:
            data = base64.b64decode(pubsub_message["data"]).decode("utf-8")
            logging.info(f"Successfully decoded message data: {data}")
        except Exception as e:
            logging.error(f"Error decoding base64 message data: {e}", exc_info=True) # exc_info=True fügt den Stack Trace hinzu


    # Später wird hier die eigentliche Logik des Agenten stehen:
    # 1. Nachricht dekodieren (Task-Objekt)
    # 2. In Firestore speichern/aktualisieren
    # 3. Ggf. neue Aufgaben an andere Agenten delegieren
    
    # Eine leere "204 No Content"-Antwort signalisiert Pub/Sub,
    # dass die Nachricht erfolgreich empfangen wurde und nicht erneut gesendet werden muss.
    return "", 204

if __name__ == "__main__":
    # Startet den Server. Cloud Run setzt automatisch den PORT.
    # Lokal würde er auf Port 8080 laufen.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))