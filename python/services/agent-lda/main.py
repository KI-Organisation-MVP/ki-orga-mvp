import os
import base64
import json
import logging
from fastapi import FastAPI, Request, HTTPException
from google.cloud import firestore
from google.cloud import pubsub_v1
from google.protobuf import json_format
from google.protobuf.timestamp_pb2 import Timestamp
from dotenv import load_dotenv

# Lädt die Umgebungsvariablen aus der .env-Datei im Root-Verzeichnis
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# Importiert die Protobuf-Definition für das Task-Objekt.
from kiorga.datamodel import task_pb2
from kiorga.utils.validation import validate_task

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

# === Globale Clients und Konstanten ===
# Initialisiert die Clients.
# Die Authentifizierung erfolgt automatisch über die Umgebung (z.B. Cloud Run).
db = firestore.Client()
publisher = pubsub_v1.PublisherClient()

# Lädt die Konfiguration aus Umgebungsvariablen.
# Dies ermöglicht eine flexible Konfiguration ohne Code-Änderungen.
PROJECT_ID = os.environ.get("GCP_PROJECT")
AGENT_ID = os.environ.get("AGENT_ID_LDA")  # Agent LDA, der die Aufgaben zugewiesen bekommt
ASSIGNED_AGENT_ID = os.environ.get("AGENT_ID_SDA_BE") # Agent SDA_BE, der die Aufgaben zugewiesen bekommt
DELEGATION_TOPIC = os.environ.get("TOPIC_SDA_BE_TASKS")  # Topic für die Delegation von Aufgaben an den Agenten SDA_BE

# Stellt sicher, dass alle notwendigen Umgebungsvariablen gesetzt sind.
if not all([PROJECT_ID, ASSIGNED_AGENT_ID, DELEGATION_TOPIC]):
    raise EnvironmentError("Fehlende Umgebungsvariablen: GCP_PROJECT, ASSIGNED_AGENT_ID, DELEGATION_TOPIC müssen gesetzt sein.")

# Initialisiert die Web-Anwendung
app = FastAPI()


def decode_pubsub_message(envelope: dict) -> str:
    """Extrahiert und dekodiert die Base64-kodierten Daten aus einer Pub/Sub-Nachricht."""
    if not isinstance(envelope, dict) or "message" not in envelope:
        raise ValueError("invalid Pub/Sub message format")

    pubsub_message = envelope["message"]
    if not isinstance(pubsub_message, dict) or "data" not in pubsub_message:
        raise ValueError("Pub/Sub message missing 'data' field")

    try:
        # Die 'data'-Nutzlast einer Pub/Sub-Nachricht ist immer base64-kodiert.
        data_bytes = base64.b64decode(pubsub_message["data"])
        logging.info(f"Empfangene Nachrichten-DNA (Hex): {data_bytes.hex()}")
        # Wir erwarten, dass die dekodierten Daten ein UTF-8-kodierter JSON-String sind.
        json_string_received = data_bytes.decode('utf-8')
        logging.info(f"Empfangene JSON-Daten: {json_string_received}")
        return json_string_received
    except Exception as e:
        logging.error(f"Base64-Dekodierung fehlgeschlagen: {e}", exc_info=True)
        raise ValueError("base64 decode error") from e


def parse_and_validate_task(json_string: str) -> task_pb2.Task:
    """Parst einen JSON-String in ein Task-Objekt und validiert dessen Inhalt."""
    try:
        task = task_pb2.Task()
        # json_format.Parse parst den JSON-String direkt in das Protobuf-Objekt.
        json_format.Parse(json_string, task)
        logging.info(f"Successfully parsed Task object from JSON: id={task.task_id}, title='{task.title}'")
    except Exception as e:
        logging.error(f"Protobuf-Deserialisierung fehlgeschlagen: {e}", exc_info=True)
        raise ValueError("protobuf parse error") from e

    # Stellt sicher, dass der Task alle für die Verarbeitung notwendigen Felder enthält.
    validation_errors = validate_task(task)
    if validation_errors:
        error_msg = f"Fehlerhafte Felder: {validation_errors}"
        logging.error(error_msg)
        raise ValueError(error_msg)
    
    logging.info("Task-Objekt erfolgreich validiert.")
    logging.info(f"Task-Details: ID={task.task_id}, Title='{task.title}', Status={task.status}, Priority={task.priority}, Creator='{task.creator_agent_id}'")
    return task


def save_task_to_firestore(db_client, task: task_pb2.Task):
    """
    Speichert den Task in Firestore und prüft auf Idempotenz.

    Ein Task gilt als bereits verarbeitet, wenn er in Firestore existiert
    und ihm bereits ein Agent zugewiesen wurde.

    Returns:
        Tuple[DocumentReference, bool]: Ein Tupel, das die Dokumentenreferenz
        und einen Boolean enthält, der angibt, ob die Verarbeitung fortgesetzt
        werden soll (True) oder nicht (False).
    """
    try:
        task_dict = json_format.MessageToDict(task)
        doc_ref = db_client.collection("tasks").document(task.task_id)

        # IDEMPOTENZ-PRÜFUNG: Verhindert die doppelte Verarbeitung derselben Nachricht.
        # Wenn der Task bereits einem Agenten zugewiesen wurde, wird die Verarbeitung gestoppt.
        task_snapshot = doc_ref.get()
        if task_snapshot.exists and task_snapshot.to_dict().get("assignedToAgentId"):
            logging.warning(f"Task {task.task_id} wurde bereits an {task_snapshot.to_dict().get('assignedToAgentId')} zugewiesen. Breche die Verarbeitung ab.")
            return doc_ref, False # Nicht weiterverarbeiten

        # Speichert den Task. `merge=True` erstellt das Dokument, falls es nicht existiert,
        # oder aktualisiert es, ohne vorhandene Felder zu überschreiben.
        doc_ref.set(task_dict, merge=True)
        logging.info(f"Task {task.task_id} successfully saved/updated in Firestore.")
        return doc_ref, True # Weiterverarbeiten
    except Exception as e:
        logging.error(f"Fehler beim Speichern in Firestore: {e}", exc_info=True)
        raise IOError("Firestore write error") from e


def delegate_task_to_sda(pub_client, project_id: str, topic: str, task_json: str, task_id: str):
    """
    Delegiert den Task an den nächsten Agenten, indem er ihn auf ein Pub/Sub-Topic veröffentlicht.
    
    Die Nachricht wird als JSON-String gesendet, um die Kompatibilität mit verschiedenen
    Subscriber-Typen zu gewährleisten.
    """
    if not task_id:
        logging.warning("Keine Task-ID vorhanden, Delegation wird übersprungen.")
        return

    logging.info(f"Delegating task {task_id} to {ASSIGNED_AGENT_ID}...")
    try:
        data_to_send = task_json.encode('utf-8')
        topic_path = pub_client.topic_path(project_id, topic)
        
        # Veröffentlicht die Nachricht. Die `publish`-Methode ist asynchron.
        future = pub_client.publish(topic_path, data=data_to_send)
        
        # `.result()` blockiert, bis die Nachricht erfolgreich veröffentlicht wurde oder ein Fehler auftritt.
        message_id = future.result(timeout=30)
        logging.info(f"Successfully delegated task to '{topic}' topic. Message ID: {message_id}")
    except Exception as e:
        logging.error(f"Fehler beim Delegieren des Tasks an Pub/Sub: {e}", exc_info=True)
        raise IOError("Pub/Sub publish error") from e


def update_task_after_delegation(doc_ref, task_id: str):
    """
    Aktualisiert den Task-Status in Firestore, nachdem er erfolgreich delegiert wurde.
    
    Setzt den Status auf "IN_PROGRESS" und vermerkt, welcher Agent zugewiesen wurde.
    """
    try:
        update_data = {
            "status": task_pb2.TaskStatus.TASK_STATUS_IN_PROGRESS,
            "assignedToAgentId": ASSIGNED_AGENT_ID,
            # Setzt den Zeitstempel auf die serverseitige Zeit von Firestore.
            "updated_at": firestore.SERVER_TIMESTAMP
        }
        doc_ref.update(update_data)
        logging.info(f"Task {task_id} status updated to IN_PROGRESS and assigned to {ASSIGNED_AGENT_ID}.")
    except Exception as e:
        logging.error(f"Fehler beim Aktualisieren des Tasks in Firestore: {e}", exc_info=True)
        raise IOError("Firestore update error") from e


@app.post("/")
async def index(request: Request):
    """
    Haupt-Endpunkt, der Pub/Sub-Nachrichten über einen HTTP-POST-Request empfängt.
    
    Der Workflow ist wie folgt:
    1. Empfängt und validiert die eingehende Pub/Sub-Nachricht.
    2. Dekodiert und parst den Task aus der Nachricht.
    3. Speichert den Task in Firestore (Idempotenz-Prüfung).
    4. Delegiert den Task an den nächsten Agenten via Pub/Sub.
    5. Aktualisiert den Task-Status in Firestore.
    """
    envelope = await request.json()
    if not envelope:
        msg = "no Pub/Sub message received"
        logging.error(msg)
        raise HTTPException(status_code=400, detail=f"Bad Request: {msg}")

    try:
        # Schritt 1 & 2: Nachricht dekodieren und Task validieren
        json_string_received = decode_pubsub_message(envelope)
        task = parse_and_validate_task(json_string_received)
        
        # Schritt 3: Task in Firestore speichern und auf Duplikate prüfen
        doc_ref, should_process = save_task_to_firestore(db, task)
        if not should_process:
            # Idempotenz: Task wurde bereits verarbeitet, daher wird die Nachricht
            # bestätigt (204), aber keine weitere Aktion ausgeführt.
            return "", 204 

        # Schritt 4: Task an den zuständigen Bearbeitungs-Agenten weiterleiten
        delegate_task_to_sda(publisher, PROJECT_ID, DELEGATION_TOPIC, json_string_received, task.task_id)
        
        # Schritt 5: Status in Firestore aktualisieren, um die Zuweisung zu bestätigen
        update_task_after_delegation(doc_ref, task.task_id)

    except ValueError as e:
        # Fehler bei der Dekodierung, beim Parsen oder bei der Validierung.
        # Gibt 400 für Dekodierungsfehler und 422 für Validierungsfehler zurück.
        status_code = 400 if "decode" in str(e) else 422
        raise HTTPException(status_code=status_code, detail=f"Bad Request: {e}")
    except IOError as e:
        # Fehler bei externen Diensten wie Firestore oder Pub/Sub.
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")
    except Exception as e:
        # Fängt alle anderen unerwarteten Fehler ab.
        logging.error(f"Unerwarteter Fehler beim Verarbeiten der Pub/Sub-Nachricht: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error: unexpected error")

    # Eine leere "204 No Content"-Antwort signalisiert Pub/Sub,
    # dass die Nachricht erfolgreich verarbeitet wurde und nicht erneut zugestellt werden muss.
    return "", 204

# Um die Anwendung zu starten, verwenden Sie:
# uvicorn main:app --host 0.0.0.0 --port 8080
