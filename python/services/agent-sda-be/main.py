import os
import logging

from fastapi import FastAPI, Request, HTTPException
from google.cloud import firestore
from google.cloud import pubsub_v1
from dotenv import load_dotenv

from service import TaskHandler

# Lädt die Umgebungsvariablen aus der .env-Datei im Root-Verzeichnis
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# === Logging-Konfiguration ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# === Globale Clients und Konfiguration ===
try:
    db = firestore.Client()
    publisher = pubsub_v1.PublisherClient()

    PROJECT_ID = os.environ["GCP_PROJECT"]
    AGENT_ID = os.environ["AGENT_ID_SDA_BE"]
    REPORTS_TOPIC = os.environ["TOPIC_REPORTS"]
except KeyError as e:
    raise EnvironmentError(f"Fehlende Umgebungsvariable: {e}") from e

# === Service-Layer Initialisierung ===
task_handler = TaskHandler(
    db_client=db,
    pub_client=publisher,
    project_id=PROJECT_ID,
    agent_id=AGENT_ID,
    reports_topic=REPORTS_TOPIC
)

# === FastAPI-Anwendung ===
app = FastAPI()

@app.post("/")
async def index(request: Request):
    """
    Empfängt eine Pub/Sub-Nachricht und übergibt sie zur Verarbeitung an den Service-Layer.
    """
    envelope = await request.json()
    if not envelope:
        raise HTTPException(status_code=400, detail="Bad Request: no Pub/Sub message received")

    try:
        task_handler.handle_task(envelope)
        return "", 204

    except ValueError as e:
        # Fehler beim Parsen der Nachricht -> Bad Request
        raise HTTPException(status_code=400, detail=f"Bad Request: {e}")
    except IOError as e:
        # Fehler bei I/O-Operationen (Firestore, Pub/Sub) -> Internal Server Error
        # Die Nachricht wird von Pub/Sub erneut zugestellt.
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")
    except Exception as e:
        # Alle anderen unerwarteten Fehler.
        logging.error(f"Unerwarteter Fehler bei der Verarbeitung der Nachricht: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error: unexpected error")

# Um die Anwendung zu starten, verwenden Sie:
# uvicorn main:app --host 0.0.0.0 --port 8080
