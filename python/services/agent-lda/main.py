import os
import logging
import google.cloud.logging
from fastapi import FastAPI, Request, HTTPException
from google.cloud import firestore
from google.cloud import pubsub_v1
from dotenv import load_dotenv

from service import TaskProcessor

# Lädt die Umgebungsvariablen aus der .env-Datei im Root-Verzeichnis
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# === Logging-Konfiguration ===
# Richtet das strukturierte Logging für Google Cloud ein.
# Dies sorgt dafür, dass Logs als JSON-Payloads gesendet werden, was die
# Filterung und Analyse in der Google Cloud Console erheblich verbessert.
client = google.cloud.logging.Client()
client.setup_logging(log_level=logging.INFO)

# === Globale Clients und Konfiguration ===
try:
    db = firestore.Client()
    publisher = pubsub_v1.PublisherClient()

    PROJECT_ID = os.environ["GCP_PROJECT"]
    DELEGATION_TOPIC = os.environ["TOPIC_SDA_BE_TASKS"]
    ASSIGNED_AGENT_ID = os.environ["AGENT_ID_SDA_BE"]
except KeyError as e:
    raise EnvironmentError(f"Fehlende Umgebungsvariable: {e}") from e

# === Service-Layer Initialisierung ===
task_processor = TaskProcessor(
    db_client=db,
    pub_client=publisher,
    project_id=PROJECT_ID,
    delegation_topic=DELEGATION_TOPIC,
    assigned_agent_id=ASSIGNED_AGENT_ID
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
        msg = "no Pub/Sub message received"
        logging.error(msg)
        raise HTTPException(status_code=400, detail=f"Bad Request: {msg}")

    try:
        task_processor.process_task(envelope)
    except ValueError as e:
        status_code = 400 if "decode" in str(e) or "format" in str(e) else 422
        raise HTTPException(status_code=status_code, detail=f"Bad Request: {e}")
    except IOError as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")
    except Exception as e:
        logging.error(f"Unerwarteter Fehler: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error: unexpected error")

    return "", 204

# Um die Anwendung zu starten, verwenden Sie:
# uvicorn main:app --host 0.0.0.0 --port 8080
