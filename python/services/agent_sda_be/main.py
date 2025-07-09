import os
import logging
import google.cloud.logging

from google.cloud import firestore
from google.cloud import pubsub_v1
from dotenv import load_dotenv

from service import TaskHandler
from kiorga.utils.fastapi_factory import create_app

# Lädt die Umgebungsvariablen aus der .env-Datei im Root-Verzeichnis
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# === Logging-Konfiguration ===
# Richtet das strukturierte Logging für Google Cloud ein.
client = google.cloud.logging.Client()
client.setup_logging(log_level=logging.INFO)

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

# === FastAPI-Anwendung über Factory erstellen ===
app = create_app(service_handler=task_handler, process_method_name="handle_task")

# Um die Anwendung zu starten, verwenden Sie:
# uvicorn main:app --host 0.0.0.0 --port 8080
