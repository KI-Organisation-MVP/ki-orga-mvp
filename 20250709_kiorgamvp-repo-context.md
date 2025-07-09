
## Directory: `.github/workflows`

### `gcp-auth-test.yml`
```yaml
# Name des Workflows, wie er in der GitHub-Oberfläche angezeigt wird
name: GCP Auth Test

# Dieser Trigger erlaubt es uns, den Workflow manuell zu starten
on:
  workflow_dispatch:

# Definiert die Berechtigungen, die der Workflow selbst von GitHub benötigt
permissions:
  contents: read
  id-token: write # Erlaubt dem Workflow, ein OIDC ID-Token von GitHub anzufordern

jobs:
  test-gcp-authentication:
    # Der Name des Jobs
    name: Authenticate with GCP and run gcloud command
    # Wir führen diesen Job auf einem von GitHub bereitgestellten Linux-Runner aus
    runs-on: ubuntu-latest

    steps:
      # Schritt 1: Authentifizierung bei Google Cloud
      # Dies ist die offizielle Action von Google, die die Magie der Workload Identity Federation nutzt
      - name: Authenticate to Google Cloud
        id: auth
        uses: google-github-actions/auth@v2
        with:
          # Hier verwenden wir die Secrets, die du in GitHub angelegt hast
          workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}
          service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}

      # Schritt 2: gcloud-Befehl ausführen, um die Authentifizierung zu testen
      # Wenn dieser Schritt erfolgreich ist, hat die Authentifizierung funktioniert
      - name: Run gcloud info command
        run: |
          echo "Successfully authenticated with a token for the following service account:"
          gcloud auth list
          echo "----------------------------------------"
          echo "Verifying access to project details..."
          gcloud projects describe ${{ secrets.GCP_PROJECT_ID }}
```

---


## Directory: `.`

### `buf.yaml`
```yaml
version: v1
lint:
  # Wir verwenden die moderne, empfohlene Standard-Regelgruppe
  use:
    - STANDARD
  # Wir behalten die Ausnahme für die Versions-Endung bei
  except:
    - PACKAGE_VERSION_SUFFIX
```

---

### `cloudbuild-pr.yaml`
```yaml
# cloudbuild-pr.yaml
# Diese Pipeline wird für Pull-Request-Checks verwendet.
# Sie führt nur Linting und (zukünftig) Tests aus, um schnelle Feedback-Zyklen zu gewährleisten.

steps:
  # =================================================================
  # SCHRITT 1: Protobuf-Dateien auf Qualität und Konsistenz prüfen
  # =================================================================
  - name: 'gcr.io/cloud-builders/wget'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        echo "Lade die fertige 'buf'-Anwendung (v1.54.0) herunter..."
        wget https://github.com/bufbuild/buf/releases/download/v1.54.0/buf-Linux-x86_64 -O /workspace/buf
        chmod +x /workspace/buf
        echo "Führe Buf Linter aus..."
        /workspace/buf lint --config /workspace/buf.yaml /workspace/proto
    id: 'Lint Proto Files'

  # =================================================================
  # SCHRITT 2: Python Linting & Tests (Platzhalter)
  # =================================================================
  # TODO: Fügen Sie hier Schritte für das Linting (z.B. mit black, isort, ruff)
  # und das Ausführen von Unit-Tests (z.B. mit pytest) hinzu.
  # Beispiel für die Zukunft:
  # - name: 'python:3.11'
  #   entrypoint: 'bash'
  #   args:
  #     - '-c'
  #     - |
  #       pip install -r python/requirements.txt
  #       pip install -r python/services/agent_lda/requirements.txt
  #       pip install -r python/services/agent_sda_be/requirements.txt
  #       pip install pytest ruff
  #       ruff check .
  #       pytest python/services/
  #   id: 'Lint and Test Python Code'

options:
  logging: CLOUD_LOGGING_ONLY 

```

---

### `cloudbuild.yaml`
```yaml
# =================================================================
# YAML-Anker und Vorlagen für wiederverwendbare Schritte
# Die `x-` Präfixe sind eine Konvention für nicht-standardisierte YAML-Erweiterungen.
# Wir definieren hier Vorlagen für die Build-, Push- und Deploy-Schritte.
# Diese Vorlagen verwenden Cloud Build-Substitutionsvariablen (`${_SERVICE_NAME}`, etc.),
# die in den jeweiligen Schritten unten mit konkreten Werten gefüllt werden.
# =================================================================
x-build-step: &build_step
  name: 'gcr.io/cloud-builders/docker'
  args:
    - 'build'
    - '--build-arg'
    - 'SERVICE_NAME=${_SERVICE_PATH_NAME}'
    - '-t'
    - 'europe-west3-docker.pkg.dev/$PROJECT_ID/agent-images/${_SERVICE_NAME}:$BUILD_ID'
    - '-f'
    - 'python/Dockerfile.generic'
    - '.'

x-push-step: &push_step
  name: 'gcr.io/cloud-builders/docker'
  args:
    - 'push'
    - 'europe-west3-docker.pkg.dev/$PROJECT_ID/agent-images/${_SERVICE_NAME}:$BUILD_ID'

x-deploy-step: &deploy_step
  name: 'gcr.io/cloud-builders/gcloud'
  args:
    - 'run'
    - 'deploy'
    - '${_SERVICE_NAME}'
    - '--image'
    - 'europe-west3-docker.pkg.dev/$PROJECT_ID/agent-images/${_SERVICE_NAME}:$BUILD_ID'
    - '--region'
    - 'europe-west3'
    - '--platform'
    - 'managed'
    - '--allow-unauthenticated'
    - '--set-env-vars=GCP_PROJECT=${PROJECT_ID},AGENT_ID_SDA_BE=agent_sda_be,AGENT_ID_LDA=agent_lda,TOPIC_REPORTS=final_reports,TOPIC_SDA_BE_TASKS=sda_be_tasks,TOPIC_LDA_TASKS=lda_tasks,TOPIC_TASK_ASSIGNMENTS=task_assignments'

# =================================================================
# Diese Datei definiert die Schritte, die Google Cloud Build ausführen soll,
# wenn ein Push auf den Branch 'main' erfolgt.
# Sie baut ein Docker-Image für den LDA-Service und pusht es in das Artifact Registry.
# Die Protobuf-Dateien werden auf Qualität und Konsistenz geprüft, bevor das Image gebaut wird.
# Die Protobuf-Dateien befinden sich im Verzeichnis 'proto' und die Dockerfile im Verzeichnis 'python/services/agent_lda'.
# Die fertige 'buf'-Anwendung wird heruntergeladen und verwendet, um die Protobuf-Dateien zu prüfen.
# Die Docker-Images werden in der Region 'europe-west3' gespeichert.
# Die Images werden in das Artifact Registry unter dem Pfad 'europe-west3-docker.pkg.dev/$PROJECT_ID/agent-images/lda-service:$BUILD_ID' gepusht.
# =================================================================
steps:
  # =================================================================
  # SCHRITT 1: Protobuf-Dateien auf Qualität und Konsistenz prüfen
  # (Neue, robustere Methode)
  # =================================================================
  - name: 'gcr.io/cloud-builders/wget'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        echo "Lade die fertige 'buf'-Anwendung (v1.54.0) herunter..."
        # Wir laden eine spezifische, aktuelle und stabile Version von buf für Linux
        wget https://github.com/bufbuild/buf/releases/download/v1.54.0/buf-Linux-x86_64 -O /workspace/buf
        
        echo "Mache 'buf' ausführbar..."
        chmod +x /workspace/buf
        
        echo "Führe Buf Linter aus..."
        # Wir führen die heruntergeladene Datei direkt aus
        # /workspace/buf lint --path proto
        # cd proto && /workspace/buf lint
        /workspace/buf lint --config /workspace/buf.yaml /workspace/proto
    id: 'Lint Proto Files'

  # =================================================================
  # SCHRITTE für lda-service
  # =================================================================
  - <<: *build_step
    id: 'Build Docker Image for LDA'
    substitutions:
      _SERVICE_NAME: 'lda-service'
      _SERVICE_PATH_NAME: 'agent_lda'

  - <<: *push_step
    id: 'Push Docker Image for LDA'
    substitutions:
      _SERVICE_NAME: 'lda-service'

  - <<: *deploy_step
    id: 'Deploy LDA to Cloud Run'
    substitutions:
      _SERVICE_NAME: 'lda-service'

  # =================================================================
  # SCHRITTE für sda-be-service
  # =================================================================
  - <<: *build_step
    id: 'Build Docker Image for SDA_BE'
    substitutions:
      _SERVICE_NAME: 'sda-be-service'
      _SERVICE_PATH_NAME: 'agent_sda_be'

  - <<: *push_step
    id: 'Push Docker Image for SDA_BE'
    substitutions:
      _SERVICE_NAME: 'sda-be-service'

  - <<: *deploy_step
    id: 'Deploy SDA_BE to Cloud Run'
    substitutions:
      _SERVICE_NAME: 'sda-be-service'

images:
  - 'europe-west3-docker.pkg.dev/$PROJECT_ID/agent-images/lda-service:$BUILD_ID'
  - 'europe-west3-docker.pkg.dev/$PROJECT_ID/agent-images/sda-be-service:$BUILD_ID'

options:
  logging: CLOUD_LOGGING_ONLY
```

---


## Directory: `proto/kiorga/datamodel`

### `decision_log.proto`
```protobuf
// Generated by the protocol buffer compiler.  DO NOT EDIT!
// source: kiorga/datamodel/decision_log.proto
syntax = "proto3";

package kiorga.datamodel;

import "google/protobuf/timestamp.proto";

// Protokolliert eine einzelne, nachvollziehbare Entscheidung oder Beobachtung
// eines Agenten während der Bearbeitung einer Aufgabe.
message DecisionLog {
  // Die eindeutige ID dieses Log-Eintrags.
  string decision_id = 1;

  // Die ID des Tasks, zu dem dieser Log-Eintrag gehört.
  // Essentiell für die Zuordnung und für Abfragen.
  string task_id = 2;

  // Der exakte Zeitstempel, wann der Eintrag vom Agenten erstellt wurde.
  google.protobuf.Timestamp logged_at = 3;

  // Die ID des Agenten, der diesen Eintrag erstellt hat.
  string creator_agent_id = 4;

  // Die eigentliche Entscheidung oder durchgeführte Aktion, kurz und prägnant.
  // Z.B.: "Starte Code-Analyse mit dem Linter-Tool."
  string decision = 5;

  // Die Begründung für die Entscheidung. Das "Warum".
  // Z.B.: "Gemäß Task-Beschreibung ist eine statische Code-Analyse erforderlich."
  string reasoning = 6;

  // Eine Liste von verworfenen Alternativen, die ebenfalls in Betracht
  // gezogen wurden. Z.B.: ["Manuelle Prüfung des Codes", "Einen anderen Linter verwenden"]
  repeated string alternatives_considered = 7;
}
```

---

### `feedback_log.proto`
```protobuf
// Generated by the protocol buffer compiler.  DO NOT EDIT!
// source: kiorga/datamodel/feedback_log.proto
syntax = "proto3";

package kiorga.datamodel;

import "google/protobuf/timestamp.proto";

// Enum zur Definition der möglichen Feedback-Geber.
enum Submitter {
  SUBMITTER_UNSPECIFIED = 0; // Standardwert
  SUBMITTER_MARCEL = 1;
  SUBMITTER_PHILIPP = 2;
}

// Enum zur Definition der quantitativen Bewertungsskala im Feedback.
enum FeedbackRating {
  FEEDBACK_RATING_UNSPECIFIED = 0; // Standardwert, falls kein Rating gegeben wird
  FEEDBACK_RATING_VERY_POOR = 1;                   // Sehr schlecht
  FEEDBACK_RATING_POOR = 2;                        // Schlecht
  FEEDBACK_RATING_NEUTRAL = 3;                     // Neutral / Ok
  FEEDBACK_RATING_GOOD = 4;                        // Gut
  FEEDBACK_RATING_VERY_GOOD = 5;                   // Sehr gut
}

// Erfasst das strukturierte, korrektive Feedback der menschlichen System-Guardianen.
message FeedbackLog {
  // Die eindeutige ID dieses Feedback-Eintrags.
  string feedback_id = 1;

  // Zeitstempel, wann das Feedback abgegeben wurde.
  google.protobuf.Timestamp submitted_at = 2;

  // Der Absender des Feedbacks.
  Submitter submitter_id = 3;

  // Optional: Die ID des Tasks, auf den sich das Feedback bezieht.
  string target_task_id = 4;

  // Der qualitative Inhalt des Feedbacks.
  string feedback_text = 5;

  // Eine optionale, quantitative Bewertung.
  FeedbackRating rating = 6;
}
```

---

### `final_report.proto`
```protobuf
// Generated by the protocol buffer compiler.  DO NOT EDIT!
// source: kiorga/datamodel/final_report.proto
syntax = "proto3";

package kiorga.datamodel;

import "google/protobuf/timestamp.proto";

// Ein Enum, das den endgültigen Ausgang einer Aufgabe klar definiert.
enum FinalStatus {
  // Standardwert, sollte nicht verwendet werden.
  FINAL_STATUS_UNSPECIFIED = 0;
  // Die Aufgabe wurde vollständig und erfolgreich abgeschlossen.
  FINAL_STATUS_SUCCESS = 1;
  // Die Aufgabe konnte nicht erfolgreich abgeschlossen werden.
  FINAL_STATUS_FAILURE = 2;
}

// Der FinalReport ist das Abschlussdokument einer Aufgabe.
message FinalReport {
  // Eindeutige ID für diesen Abschlussbericht.
  string report_id = 1;

  // Die ID des Tasks, der hiermit abgeschlossen wird.
  string task_id = 2;

  // Die ID des Agenten, der die Aufgabe ausgeführt und diesen Bericht erstellt hat.
  string executing_agent_id = 3;

  // Der Zeitstempel, wann die Aufgabe abgeschlossen wurde.
  google.protobuf.Timestamp completion_timestamp = 4;

  // Der endgültige Status der Aufgabe.
  FinalStatus final_status = 5;

  // Eine prägnante Zusammenfassung der gesamten durchgeführten Arbeit,
  // der erzielten Ergebnisse und der Gründe für einen eventuellen Fehlschlag.
  string summary = 6;

  // Eine Map von Referenzen auf die finalen Datenobjekte, die als Ergebnis
  // dieser Aufgabe erstellt wurden. Der Key ist eine beschreibende Bezeichnung,
  // der Value ist die ID des Objekts in Firestore.
  map<string, string> output_data_references = 7; // DEINE VERBESSERUNG
}
```

---

### `progress_report.proto`
```protobuf
// Generated by the protocol buffer compiler.  DO NOT EDIT!
// source: kiorga/datamodel/progress_report.proto
syntax = "proto3";

package kiorga.datamodel;

import "google/protobuf/timestamp.proto";

// Ein ProgressReport ist ein "Lebenszeichen" oder ein Zwischenbericht eines Agenten,
// der an einer Aufgabe arbeitet.
message ProgressReport {
  // Eindeutige ID für diesen spezifischen Bericht (z.B. eine UUID).
  string report_id = 1;

  // Die ID der Aufgabe (aus Task.task_id), auf die sich dieser Bericht bezieht.
  string task_id = 2;

  // Die ID des Agenten, der diesen Bericht sendet.
  string reporting_agent_id = 3;

  // Der genaue Zeitstempel, wann der Bericht erstellt wurde.
  google.protobuf.Timestamp created_at = 4;

  // Eine prägnante Zusammenfassung des aktuellen Stands und der letzten Aktivitäten.
  // z.B. "Code-Generierung für Service X abgeschlossen, starte jetzt Unit-Tests."
  string status_text = 5;

  // Eine Zahl von 0 bis 100, die den geschätzten Fortschritt anzeigt.
  int32 percentage_complete = 6;

  // Ein optionales Feld, um auf Hindernisse oder Probleme hinzuweisen,
  // die den Fortschritt verlangsamen, aber noch keinen Fehlschlag bedeuten.
  // z.B. "API-Endpunkt von Drittanbieter antwortet langsam."
  string blockers_or_issues = 7;
}
```

---

### `task.proto`
```protobuf
// Generated by the protocol buffer compiler.  DO NOT EDIT!
// source: kiorga/datamodel/task.proto
syntax = "proto3";

package kiorga.datamodel;

import "google/protobuf/timestamp.proto";

// Enum zur Definition des Bearbeitungsstatus einer Aufgabe.
enum TaskStatus {
  TASK_STATUS_UNSPECIFIED = 0;
  TASK_STATUS_PENDING = 1;
  TASK_STATUS_IN_PROGRESS = 2;
  TASK_STATUS_COMPLETED = 3;
  TASK_STATUS_FAILED = 4;
}

// Enum zur Definition der Priorität einer Aufgabe.
enum TaskPriority {
  TASK_PRIORITY_UNSPECIFIED = 0;
  TASK_PRIORITY_URGENT = 1;
  TASK_PRIORITY_HIGH = 2;
  TASK_PRIORITY_MEDIUM = 3;
  TASK_PRIORITY_LOW = 4;
  TASK_PRIORITY_OPTIONAL = 5;
}

// Das zentrale Objekt zur Steuerung und Verfolgung von Arbeit in der KI-Organisation.
message Task {
  // Die global eindeutige ID der Aufgabe (z.B. eine UUID).
  string task_id = 1;

  // Kurzer, menschenlesbarer Titel der Aufgabe, z.B. für Listenansichten.
  string title = 2;

  // Detaillierte Beschreibung der Arbeitsanweisung für den ausführenden Agenten.
  string description = 3;

  // Der aktuelle Bearbeitungsstatus der Aufgabe.
  TaskStatus status = 4;

  // Die Priorität der Aufgabe zur Steuerung der Abarbeitungsreihenfolge.
  TaskPriority priority = 5;

  // Die ID des Agenten, der für die Ausführung der Aufgabe verantwortlich ist.
  string assigned_to_agent_id = 6;

  // Die ID des Agenten, der die Aufgabe ursprünglich erstellt hat.
  string creator_agent_id = 7;

  // Zeitstempel der Erstellung der Aufgabe.
  google.protobuf.Timestamp created_at = 8;

  // Zeitstempel der letzten Aktualisierung. Wird bei jeder Änderung aktualisiert.
  google.protobuf.Timestamp updated_at = 9;

  // Eine Liste von 'task_id's, die abgeschlossen sein müssen, bevor diese Aufgabe starten kann.
  repeated string dependencies = 10;

  // Schlüssel-Wert-Paare für Verweise auf Input-Daten (z.B. Pfade in Cloud Storage).
  map<string, string> input_data_references = 11;

  // Schlüssel-Wert-Paare für Verweise auf Output-Daten.
  map<string, string> output_data_references = 12;

  // Textuelle Beschreibung der Erfolgskriterien ("Definition of Done").
  string success_criteria_metrics = 13;

  // Optional: Die ID der übergeordneten Aufgabe zur Abbildung von Hierarchien.
  string parent_task_id = 14;

  // Optional: Das Fälligkeitsdatum für die Aufgabe, um die Priorisierung zu unterstützen.
  google.protobuf.Timestamp due_date = 15;

  // Wenn 'true', erfordert die Aufgabe menschliche Freigaben an definierten Punkten.
  bool co_pilot_mode = 16;
}
```

---

### `test_result_report.proto`
```protobuf
// Generated by the protocol buffer compiler.  DO NOT EDIT!
// source: kiorga/datamodel/test_result_report.proto
syntax = "proto3";

package kiorga.datamodel;

import "google/protobuf/timestamp.proto";
import "google/protobuf/duration.proto";

// Enum für den Gesamtstatus des Testlaufs
enum TestRunStatus {
  TEST_RUN_STATUS_UNSPECIFIED = 0;
  TEST_RUN_STATUS_PASSED = 1; // Alle Tests erfolgreich
  TEST_RUN_STATUS_FAILED = 2; // Mindestens ein Test fehlgeschlagen
  TEST_RUN_STATUS_COMPLETED_WITH_WARNINGS = 3; // Alle Tests durchgelaufen, aber es gab Warnungen
}

// Repräsentiert einen einzelnen, durchgeführten Testfall
message TestCaseResult {
  string test_name = 1; // Name des Testfalls, z.B. "test_user_login_success"
  bool passed = 2; // True, wenn der Test erfolgreich war, sonst false
  google.protobuf.Duration duration = 3; // Wie lange der Test lief
  string details = 4; // Optionale Details, z.B. Fehlermeldung bei Fehlschlag
}

// Der formale Testbericht, den der QA-Agent erstellt.
message TestResultReport {
  string report_id = 1; // Eindeutige ID dieses Testberichts
  string task_id = 2; // Bezieht sich auf den ursprünglichen Task, der getestet wurde
  // Die Git Commit-ID des Quellcodes, der getestet wurde.
  string source_commit_id = 3; // UM BENANNT für mehr Klarheit
  string qaa_agent_id = 4; // ID des ausführenden QA-Agenten
  google.protobuf.Timestamp execution_timestamp = 5; // Wann wurden die Tests ausgeführt?
  TestRunStatus overall_status = 6; // Das Gesamtergebnis
  int32 total_tests_run = 7;
  int32 total_tests_passed = 8;
  repeated TestCaseResult test_cases = 9; // Eine Liste der Ergebnisse der einzelnen Testfälle
  string summary = 10; // Eine kurze Zusammenfassung in natürlicher Sprache
}
```

---


## Directory: `python`

### `create_and_publish_task.py`
```python
import uuid
import os
import logging
from dotenv import load_dotenv
from kiorga.datamodel import task_pb2
# Wir importieren die korrekten Enums
from kiorga.utils.pubsub_helpers import publish_proto_message_as_json
from kiorga.utils.validation import validate_task
from kiorga.datamodel.task_pb2 import TaskStatus, TaskPriority
from google.protobuf.timestamp_pb2 import Timestamp
from google.cloud import pubsub_v1

# Lädt die Umgebungsvariablen aus der .env-Datei im Root-Verzeichnis
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# Sauberes Logging konfigurieren
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Konfiguration ---
PROJECT_ID = os.getenv("GCP_PROJECT")
ASSIGN_TOPIC_ID = os.getenv("TOPIC_LDA_TASKS") # Topic für die Zuweisung von Aufgaben

if not all([PROJECT_ID, ASSIGN_TOPIC_ID]):
    raise EnvironmentError("Fehlende Umgebungsvariablen: GCP_PROJECT, TASK_ASSIGNMENTS_TOPIC müssen gesetzt sein.")
# ---------------------

def create_and_publish_task():
    """Erstellt ein neues Task-Objekt und veröffentlicht es direkt in Pub/Sub.
    Rückgabe: (success: bool, error_code: str|None, error_message: str|None)
    """
    
    # 1. Task-Objekt erstellen und mit Testdaten befüllen
    task = task_pb2.Task()
    task.task_id = str(uuid.uuid4())  # Eindeutige ID generieren
    task.title = "Erster Test nach der Umstellung von flask auf FastAPI"
    task.description = "Dieser Task wurde direkt aus einem Python-Skript veröffentlicht, um Encoding-Fehler zu vermeiden."
    
    # KORREKTER STATUS-WERT setzen
    task.status = TaskStatus.TASK_STATUS_PENDING
    
    task.priority = TaskPriority.TASK_PRIORITY_URGENT
    task.creator_agent_id = "system-test-script"
    
    # Aktuellen Zeitstempel setzen
    now = Timestamp()
    now.GetCurrentTime()
    task.created_at.CopyFrom(now)

    # Anwendung der Validierung vor der Serialisierung:
    validation_errors = validate_task(task)
    if validation_errors:
        error_msg = f"Fehlerhafte Felder: {validation_errors}"
        print(error_msg)
        return (False, "VALIDATION_ERROR", error_msg)

    logging.info(f"Erstelle Task mit ID: {task.task_id}")

    # 3. Nachricht mit Fehlerbehandlung an Pub/Sub veröffentlichen
    try:
        publisher = pubsub_v1.PublisherClient()
        publish_proto_message_as_json(
            publisher=publisher,
            project_id=PROJECT_ID,
            topic_id=ASSIGN_TOPIC_ID,
            proto_message=task
        )
        return (True, None, None)
    except IOError as e:
        logging.error(f"Fehler bei der Pub/Sub-API während des Veröffentlichens: {e}")
        return (False, "PUBSUB_API_ERROR", str(e))
    except Exception as e:
        logging.error(f"Ein unerwarteter Fehler ist aufgetreten: {e}")
        return (False, "UNEXPECTED_ERROR", str(e))

if __name__ == "__main__":
    # Hauptausführung: Task erstellen und veröffentlichen
    success, error_code, error_message = create_and_publish_task()
    if success:
        print("\nSkript erfolgreich ausgeführt. Nachricht wurde an Pub/Sub gesendet.")
    else:
        print(f"\nFehler bei der Ausführung des Skripts [{error_code}]: {error_message}")
```

---


## Directory: `python/kiorga`

### `__init__.py`
```python

```

---


## Directory: `python/kiorga/datamodel`

### `__init__.py`
```python

```

---

### `decision_log_pb2.py`
```python
# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: kiorga/datamodel/decision_log.proto
# Protobuf Python Version: 6.31.0
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    6,
    31,
    0,
    '',
    'kiorga/datamodel/decision_log.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import timestamp_pb2 as google_dot_protobuf_dot_timestamp__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n#kiorga/datamodel/decision_log.proto\x12\x10kiorga.datamodel\x1a\x1fgoogle/protobuf/timestamp.proto\"\xc2\x01\n\x0b\x44\x65\x63isionLog\x12\x13\n\x0b\x64\x65\x63ision_id\x18\x01 \x01(\t\x12\x0f\n\x07task_id\x18\x02 \x01(\t\x12-\n\tlogged_at\x18\x03 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12\x18\n\x10\x63reator_agent_id\x18\x04 \x01(\t\x12\x10\n\x08\x64\x65\x63ision\x18\x05 \x01(\t\x12\x11\n\treasoning\x18\x06 \x01(\t\x12\x1f\n\x17\x61lternatives_considered\x18\x07 \x03(\tb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'kiorga.datamodel.decision_log_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_DECISIONLOG']._serialized_start=91
  _globals['_DECISIONLOG']._serialized_end=285
# @@protoc_insertion_point(module_scope)

```

---

### `feedback_log_pb2.py`
```python
# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: kiorga/datamodel/feedback_log.proto
# Protobuf Python Version: 6.31.0
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    6,
    31,
    0,
    '',
    'kiorga/datamodel/feedback_log.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import timestamp_pb2 as google_dot_protobuf_dot_timestamp__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n#kiorga/datamodel/feedback_log.proto\x12\x10kiorga.datamodel\x1a\x1fgoogle/protobuf/timestamp.proto\"\xe8\x01\n\x0b\x46\x65\x65\x64\x62\x61\x63kLog\x12\x13\n\x0b\x66\x65\x65\x64\x62\x61\x63k_id\x18\x01 \x01(\t\x12\x30\n\x0csubmitted_at\x18\x02 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12\x31\n\x0csubmitter_id\x18\x03 \x01(\x0e\x32\x1b.kiorga.datamodel.Submitter\x12\x16\n\x0etarget_task_id\x18\x04 \x01(\t\x12\x15\n\rfeedback_text\x18\x05 \x01(\t\x12\x30\n\x06rating\x18\x06 \x01(\x0e\x32 .kiorga.datamodel.FeedbackRating*S\n\tSubmitter\x12\x19\n\x15SUBMITTER_UNSPECIFIED\x10\x00\x12\x14\n\x10SUBMITTER_MARCEL\x10\x01\x12\x15\n\x11SUBMITTER_PHILIPP\x10\x02*\xc0\x01\n\x0e\x46\x65\x65\x64\x62\x61\x63kRating\x12\x1f\n\x1b\x46\x45\x45\x44\x42\x41\x43K_RATING_UNSPECIFIED\x10\x00\x12\x1d\n\x19\x46\x45\x45\x44\x42\x41\x43K_RATING_VERY_POOR\x10\x01\x12\x18\n\x14\x46\x45\x45\x44\x42\x41\x43K_RATING_POOR\x10\x02\x12\x1b\n\x17\x46\x45\x45\x44\x42\x41\x43K_RATING_NEUTRAL\x10\x03\x12\x18\n\x14\x46\x45\x45\x44\x42\x41\x43K_RATING_GOOD\x10\x04\x12\x1d\n\x19\x46\x45\x45\x44\x42\x41\x43K_RATING_VERY_GOOD\x10\x05\x62\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'kiorga.datamodel.feedback_log_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_SUBMITTER']._serialized_start=325
  _globals['_SUBMITTER']._serialized_end=408
  _globals['_FEEDBACKRATING']._serialized_start=411
  _globals['_FEEDBACKRATING']._serialized_end=603
  _globals['_FEEDBACKLOG']._serialized_start=91
  _globals['_FEEDBACKLOG']._serialized_end=323
# @@protoc_insertion_point(module_scope)

```

---

### `final_report_pb2.py`
```python
# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: kiorga/datamodel/final_report.proto
# Protobuf Python Version: 6.31.0
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    6,
    31,
    0,
    '',
    'kiorga/datamodel/final_report.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import timestamp_pb2 as google_dot_protobuf_dot_timestamp__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n#kiorga/datamodel/final_report.proto\x12\x10kiorga.datamodel\x1a\x1fgoogle/protobuf/timestamp.proto\"\xe3\x02\n\x0b\x46inalReport\x12\x11\n\treport_id\x18\x01 \x01(\t\x12\x0f\n\x07task_id\x18\x02 \x01(\t\x12\x1a\n\x12\x65xecuting_agent_id\x18\x03 \x01(\t\x12\x38\n\x14\x63ompletion_timestamp\x18\x04 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12\x33\n\x0c\x66inal_status\x18\x05 \x01(\x0e\x32\x1d.kiorga.datamodel.FinalStatus\x12\x0f\n\x07summary\x18\x06 \x01(\t\x12W\n\x16output_data_references\x18\x07 \x03(\x0b\x32\x37.kiorga.datamodel.FinalReport.OutputDataReferencesEntry\x1a;\n\x19OutputDataReferencesEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01*_\n\x0b\x46inalStatus\x12\x1c\n\x18\x46INAL_STATUS_UNSPECIFIED\x10\x00\x12\x18\n\x14\x46INAL_STATUS_SUCCESS\x10\x01\x12\x18\n\x14\x46INAL_STATUS_FAILURE\x10\x02\x62\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'kiorga.datamodel.final_report_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_FINALREPORT_OUTPUTDATAREFERENCESENTRY']._loaded_options = None
  _globals['_FINALREPORT_OUTPUTDATAREFERENCESENTRY']._serialized_options = b'8\001'
  _globals['_FINALSTATUS']._serialized_start=448
  _globals['_FINALSTATUS']._serialized_end=543
  _globals['_FINALREPORT']._serialized_start=91
  _globals['_FINALREPORT']._serialized_end=446
  _globals['_FINALREPORT_OUTPUTDATAREFERENCESENTRY']._serialized_start=387
  _globals['_FINALREPORT_OUTPUTDATAREFERENCESENTRY']._serialized_end=446
# @@protoc_insertion_point(module_scope)

```

---

### `progress_report_pb2.py`
```python
# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: kiorga/datamodel/progress_report.proto
# Protobuf Python Version: 6.31.0
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    6,
    31,
    0,
    '',
    'kiorga/datamodel/progress_report.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import timestamp_pb2 as google_dot_protobuf_dot_timestamp__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n&kiorga/datamodel/progress_report.proto\x12\x10kiorga.datamodel\x1a\x1fgoogle/protobuf/timestamp.proto\"\xce\x01\n\x0eProgressReport\x12\x11\n\treport_id\x18\x01 \x01(\t\x12\x0f\n\x07task_id\x18\x02 \x01(\t\x12\x1a\n\x12reporting_agent_id\x18\x03 \x01(\t\x12.\n\ncreated_at\x18\x04 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12\x13\n\x0bstatus_text\x18\x05 \x01(\t\x12\x1b\n\x13percentage_complete\x18\x06 \x01(\x05\x12\x1a\n\x12\x62lockers_or_issues\x18\x07 \x01(\tb\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'kiorga.datamodel.progress_report_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_PROGRESSREPORT']._serialized_start=94
  _globals['_PROGRESSREPORT']._serialized_end=300
# @@protoc_insertion_point(module_scope)

```

---

### `task_pb2.py`
```python
# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: kiorga/datamodel/task.proto
# Protobuf Python Version: 6.31.0
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    6,
    31,
    0,
    '',
    'kiorga/datamodel/task.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import timestamp_pb2 as google_dot_protobuf_dot_timestamp__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1bkiorga/datamodel/task.proto\x12\x10kiorga.datamodel\x1a\x1fgoogle/protobuf/timestamp.proto\"\xe3\x05\n\x04Task\x12\x0f\n\x07task_id\x18\x01 \x01(\t\x12\r\n\x05title\x18\x02 \x01(\t\x12\x13\n\x0b\x64\x65scription\x18\x03 \x01(\t\x12,\n\x06status\x18\x04 \x01(\x0e\x32\x1c.kiorga.datamodel.TaskStatus\x12\x30\n\x08priority\x18\x05 \x01(\x0e\x32\x1e.kiorga.datamodel.TaskPriority\x12\x1c\n\x14\x61ssigned_to_agent_id\x18\x06 \x01(\t\x12\x18\n\x10\x63reator_agent_id\x18\x07 \x01(\t\x12.\n\ncreated_at\x18\x08 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12.\n\nupdated_at\x18\t \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12\x14\n\x0c\x64\x65pendencies\x18\n \x03(\t\x12N\n\x15input_data_references\x18\x0b \x03(\x0b\x32/.kiorga.datamodel.Task.InputDataReferencesEntry\x12P\n\x16output_data_references\x18\x0c \x03(\x0b\x32\x30.kiorga.datamodel.Task.OutputDataReferencesEntry\x12 \n\x18success_criteria_metrics\x18\r \x01(\t\x12\x16\n\x0eparent_task_id\x18\x0e \x01(\t\x12,\n\x08\x64ue_date\x18\x0f \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12\x15\n\rco_pilot_mode\x18\x10 \x01(\x08\x1a:\n\x18InputDataReferencesEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\x1a;\n\x19OutputDataReferencesEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01*\x92\x01\n\nTaskStatus\x12\x1b\n\x17TASK_STATUS_UNSPECIFIED\x10\x00\x12\x17\n\x13TASK_STATUS_PENDING\x10\x01\x12\x1b\n\x17TASK_STATUS_IN_PROGRESS\x10\x02\x12\x19\n\x15TASK_STATUS_COMPLETED\x10\x03\x12\x16\n\x12TASK_STATUS_FAILED\x10\x04*\xac\x01\n\x0cTaskPriority\x12\x1d\n\x19TASK_PRIORITY_UNSPECIFIED\x10\x00\x12\x18\n\x14TASK_PRIORITY_URGENT\x10\x01\x12\x16\n\x12TASK_PRIORITY_HIGH\x10\x02\x12\x18\n\x14TASK_PRIORITY_MEDIUM\x10\x03\x12\x15\n\x11TASK_PRIORITY_LOW\x10\x04\x12\x1a\n\x16TASK_PRIORITY_OPTIONAL\x10\x05\x62\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'kiorga.datamodel.task_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_TASK_INPUTDATAREFERENCESENTRY']._loaded_options = None
  _globals['_TASK_INPUTDATAREFERENCESENTRY']._serialized_options = b'8\001'
  _globals['_TASK_OUTPUTDATAREFERENCESENTRY']._loaded_options = None
  _globals['_TASK_OUTPUTDATAREFERENCESENTRY']._serialized_options = b'8\001'
  _globals['_TASKSTATUS']._serialized_start=825
  _globals['_TASKSTATUS']._serialized_end=971
  _globals['_TASKPRIORITY']._serialized_start=974
  _globals['_TASKPRIORITY']._serialized_end=1146
  _globals['_TASK']._serialized_start=83
  _globals['_TASK']._serialized_end=822
  _globals['_TASK_INPUTDATAREFERENCESENTRY']._serialized_start=703
  _globals['_TASK_INPUTDATAREFERENCESENTRY']._serialized_end=761
  _globals['_TASK_OUTPUTDATAREFERENCESENTRY']._serialized_start=763
  _globals['_TASK_OUTPUTDATAREFERENCESENTRY']._serialized_end=822
# @@protoc_insertion_point(module_scope)

```

---

### `test_result_report_pb2.py`
```python
# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: kiorga/datamodel/test_result_report.proto
# Protobuf Python Version: 6.31.0
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    6,
    31,
    0,
    '',
    'kiorga/datamodel/test_result_report.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import timestamp_pb2 as google_dot_protobuf_dot_timestamp__pb2
from google.protobuf import duration_pb2 as google_dot_protobuf_dot_duration__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n)kiorga/datamodel/test_result_report.proto\x12\x10kiorga.datamodel\x1a\x1fgoogle/protobuf/timestamp.proto\x1a\x1egoogle/protobuf/duration.proto\"q\n\x0eTestCaseResult\x12\x11\n\ttest_name\x18\x01 \x01(\t\x12\x0e\n\x06passed\x18\x02 \x01(\x08\x12+\n\x08\x64uration\x18\x03 \x01(\x0b\x32\x19.google.protobuf.Duration\x12\x0f\n\x07\x64\x65tails\x18\x04 \x01(\t\"\xd4\x02\n\x10TestResultReport\x12\x11\n\treport_id\x18\x01 \x01(\t\x12\x0f\n\x07task_id\x18\x02 \x01(\t\x12\x18\n\x10source_commit_id\x18\x03 \x01(\t\x12\x14\n\x0cqaa_agent_id\x18\x04 \x01(\t\x12\x37\n\x13\x65xecution_timestamp\x18\x05 \x01(\x0b\x32\x1a.google.protobuf.Timestamp\x12\x37\n\x0eoverall_status\x18\x06 \x01(\x0e\x32\x1f.kiorga.datamodel.TestRunStatus\x12\x17\n\x0ftotal_tests_run\x18\x07 \x01(\x05\x12\x1a\n\x12total_tests_passed\x18\x08 \x01(\x05\x12\x34\n\ntest_cases\x18\t \x03(\x0b\x32 .kiorga.datamodel.TestCaseResult\x12\x0f\n\x07summary\x18\n \x01(\t*\x95\x01\n\rTestRunStatus\x12\x1f\n\x1bTEST_RUN_STATUS_UNSPECIFIED\x10\x00\x12\x1a\n\x16TEST_RUN_STATUS_PASSED\x10\x01\x12\x1a\n\x16TEST_RUN_STATUS_FAILED\x10\x02\x12+\n\'TEST_RUN_STATUS_COMPLETED_WITH_WARNINGS\x10\x03\x62\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'kiorga.datamodel.test_result_report_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_TESTRUNSTATUS']._serialized_start=587
  _globals['_TESTRUNSTATUS']._serialized_end=736
  _globals['_TESTCASERESULT']._serialized_start=128
  _globals['_TESTCASERESULT']._serialized_end=241
  _globals['_TESTRESULTREPORT']._serialized_start=244
  _globals['_TESTRESULTREPORT']._serialized_end=584
# @@protoc_insertion_point(module_scope)

```

---


## Directory: `python/kiorga/utils`

### `fastapi_factory.py`
```python
import logging
from fastapi import FastAPI, Request, HTTPException

def create_app(service_handler: object, process_method_name: str) -> FastAPI:
    """
    Erstellt und konfiguriert eine FastAPI-Anwendung mit einem generischen Pub/Sub-Endpunkt.

    Diese Factory zentralisiert die Erstellung der App, das Routing und die Fehlerbehandlung
    für alle Pub/Sub-basierten Services.

    Args:
        service_handler: Eine Instanz der Service-Klasse (z.B. TaskProcessor, TaskHandler).
        process_method_name: Der Name der Methode auf dem Service-Handler, die die
                             eigentliche Verarbeitungslogik enthält (z.B. "process_task").

    Returns:
        Eine konfigurierte FastAPI-Anwendungsinstanz.
    """
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
            handler_method = getattr(service_handler, process_method_name)
            handler_method(envelope)
            return "", 204
        except ValueError as e:
            logging.warning(f"Bad Request bei der Verarbeitung: {e}")
            raise HTTPException(status_code=400, detail=f"Bad Request: {e}")
        except IOError as e:
            logging.error(f"IO-Fehler bei der Verarbeitung: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")
        except Exception as e:
            logging.error(f"Unerwarteter Fehler bei der Verarbeitung: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal Server Error: unexpected error")

    return app
```

---

### `pubsub_helpers.py`
```python
import base64
import logging
import time
from datetime import datetime

from google.api_core import exceptions
from google.cloud import pubsub_v1
from google.protobuf import json_format
from google.protobuf.message import Message

def decode_pubsub_message(envelope: dict) -> tuple[str, float]:
    """
    Dekodiert eine Pub/Sub-Nachrichtenhülle (Envelope).

    Extrahiert und dekodiert die Base64-kodierten Daten aus einer Pub/Sub-Nachricht
    und gibt den resultierenden JSON-String sowie den Veröffentlichungszeitstempel zurück.

    Args:
        envelope: Die Pub/Sub-Nachrichtenhülle als Dictionary.

    Returns:
        Ein Tupel, das den dekodierten JSON-String und den Veröffentlichungszeitstempel
        als Float enthält.

    Raises:
        ValueError: Wenn das Nachrichtenformat ungültig ist oder die Dekodierung fehlschlägt.
    """
    if not isinstance(envelope, dict) or "message" not in envelope:
        raise ValueError("invalid Pub/Sub message format")

    pubsub_message = envelope["message"]
    if not isinstance(pubsub_message, dict) or "data" not in pubsub_message:
        raise ValueError("Pub/Sub message missing 'data' field")

    publish_time_str = pubsub_message.get("publish_time")
    publish_timestamp = time.time()  # Fallback auf aktuelle Zeit
    if publish_time_str:
        try:
            # Korrekter Umgang mit 'Z' für die UTC-Zeitzone
            dt_object = datetime.fromisoformat(publish_time_str.replace('Z', '+00:00'))
            publish_timestamp = dt_object.timestamp()
        except ValueError:
            logging.warning(f"Konnte publish_time '{publish_time_str}' nicht parsen. Verwende Fallback.")

    try:
        data_bytes = base64.b64decode(pubsub_message["data"])
        json_string_received = data_bytes.decode('utf-8')
        return json_string_received, publish_timestamp
    except Exception as e:
        logging.error(f"Base64-Dekodierung fehlgeschlagen: {e}", exc_info=True)
        raise ValueError("base64 decode error") from e


def publish_proto_message_as_json(
    publisher: pubsub_v1.PublisherClient,
    project_id: str,
    topic_id: str,
    proto_message: Message,
) -> str:
    """
    Serialisiert eine Protobuf-Nachricht nach JSON, kodiert sie und veröffentlicht sie in Pub/Sub.

    Args:
        publisher: Eine Instanz des pubsub_v1.PublisherClient.
        project_id: Die Google Cloud Projekt-ID.
        topic_id: Die ID des Pub/Sub-Topics.
        proto_message: Die zu sendende Protobuf-Nachricht.

    Returns:
        Die Message-ID der veröffentlichten Nachricht.

    Raises:
        IOError: Wenn das Veröffentlichen in Pub/Sub fehlschlägt.
        ValueError: Wenn die Serialisierung der Nachricht fehlschlägt.
    """
    try:
        # 1. Protobuf-Nachricht in einen JSON-String konvertieren.
        json_string = json_format.MessageToJson(proto_message)
        data_to_send = json_string.encode("utf-8")

        # 2. Nachricht veröffentlichen.
        topic_path = publisher.topic_path(project_id, topic_id)
        future = publisher.publish(topic_path, data=data_to_send)
        message_id = future.result(timeout=30)
        logging.info(f"Nachricht erfolgreich an Topic '{topic_id}' veröffentlicht. Message ID: {message_id}")
        return message_id
    except exceptions.GoogleAPICallError as e:
        logging.error(f"Fehler bei der Pub/Sub-API während des Veröffentlichens an Topic '{topic_id}': {e}")
        raise IOError(f"Pub/Sub API error on topic {topic_id}") from e
    except Exception as e:
        logging.error(f"Ein unerwarteter Fehler ist beim Veröffentlichen an Topic '{topic_id}' aufgetreten: {e}")
        raise IOError(f"Unexpected error publishing to topic {topic_id}") from e
```

---

### `validation.py`
```python
import logging
from typing import Callable, List, Optional, Type, TypeVar

from kiorga.datamodel import task_pb2
from google.protobuf import json_format
from google.protobuf.message import Message

# Generic TypeVar für Protobuf-Nachrichten, um Typsicherheit zu gewährleisten
T = TypeVar('T', bound=Message)

def parse_and_validate_message(
    json_string: str,
    message_class: Type[T],
    validator_func: Optional[Callable[[T], List[str]]] = None
) -> T:
    """
    Parst einen JSON-String in eine Protobuf-Nachricht, validiert sie optional und gibt sie zurück.
    """
    try:
        message_instance = message_class()
        json_format.Parse(json_string, message_instance)
    except json_format.ParseError as e:
        logging.error(f"Protobuf-Deserialisierung für {message_class.__name__} fehlgeschlagen: {e}", exc_info=True)
        raise ValueError(f"protobuf parse error for {message_class.__name__}") from e

    if validator_func and (errors := validator_func(message_instance)):
        error_msg = f"Validierung für {message_class.__name__} fehlgeschlagen. Fehlerhafte Felder: {errors}"
        raise ValueError(error_msg)

    return message_instance

def validate_task(task: task_pb2.Task) -> list[str]:
    """
    Prüft, ob die Pflichtfelder im Task-Objekt für eine gültige Verarbeitung gesetzt sind.
    
    Gibt eine Liste von Fehlermeldungen zurück. Eine leere Liste bedeutet,
    dass der Task gültig ist.
    """
    errors = []
    if not task.task_id:
        errors.append("task_id fehlt")
    if not task.title or len(task.title.strip()) == 0:
        errors.append("title fehlt oder ist leer")
    if not task.description or len(task.description.strip()) == 0:
        errors.append("description fehlt oder ist leer")

    # Prüft, ob Status und Priorität gültige Enum-Werte sind.
    # `TASK_STATUS_UNSPECIFIED` und `TASK_PRIORITY_UNSPECIFIED` sind gültig,
    # da sie die Standardwerte sind, wenn nichts explizit gesetzt wird.
    valid_status_values = [
        task_pb2.TaskStatus.TASK_STATUS_UNSPECIFIED,
        task_pb2.TaskStatus.TASK_STATUS_PENDING,
        task_pb2.TaskStatus.TASK_STATUS_COMPLETED,
        task_pb2.TaskStatus.TASK_STATUS_IN_PROGRESS,
        task_pb2.TaskStatus.TASK_STATUS_FAILED,
    ]
    if task.status not in valid_status_values:
        errors.append(f"status ist ungültig: {task.status}")

    valid_priority_values = [
        task_pb2.TaskPriority.TASK_PRIORITY_UNSPECIFIED,
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
    # Ein gültiger Zeitstempel muss gesetzt sein.
    if not task.created_at or getattr(task.created_at, "seconds", 0) == 0:
        errors.append("created_at fehlt oder ist ungültig")
    return errors
```

---


## Directory: `python/services/agent_lda`

### `main.py`
```python
import os
import logging
import google.cloud.logging
from google.cloud import firestore
from google.cloud import pubsub_v1
from dotenv import load_dotenv

from service import TaskProcessor
from kiorga.utils.fastapi_factory import create_app

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

# === FastAPI-Anwendung über Factory erstellen ===
app = create_app(service_handler=task_processor, process_method_name="process_task")

# Um die Anwendung zu starten, verwenden Sie:
# uvicorn main:app --host 0.0.0.0 --port 8080

```

---

### `service.py`
```python
## Imports
import logging
import time

from google.cloud import firestore
from google.protobuf import json_format

from kiorga.datamodel import task_pb2
from kiorga.utils.validation import parse_and_validate_message, validate_task
from kiorga.utils.pubsub_helpers import decode_pubsub_message, publish_proto_message_as_json

class TaskProcessor:
    """
    Kapselt die Geschäftslogik für die Verarbeitung von Tasks.
    """

    def __init__(self, db_client, pub_client, project_id: str, delegation_topic: str, assigned_agent_id: str):
        """
        Initialisiert den TaskProcessor mit den erforderlichen Clients und Konfigurationen.

        Args:
            db_client: Firestore-Client.
            pub_client: Pub/Sub-Publisher-Client.
            project_id: Google Cloud Projekt-ID.
            delegation_topic: Name des Pub/Sub-Topics für die Delegierung.
            assigned_agent_id: ID des Agenten, an den die Aufgabe delegiert wird.
        """
        self.db = db_client
        self.publisher = pub_client
        self.project_id = project_id
        self.delegation_topic = delegation_topic
        self.assigned_agent_id = assigned_agent_id

    def process_task(self, envelope: dict) -> None:
        """
        Orchestriert den gesamten Prozess der Task-Verarbeitung.
        """
        start_time = time.time()
        try:
            json_string_received, publish_timestamp = decode_pubsub_message(envelope)
            # receive_latency = time.time() - publish_timestamp # Metrik entfernt

            task = parse_and_validate_message(
                json_string=json_string_received,
                message_class=task_pb2.Task,
                validator_func=validate_task
            )

            doc_ref, should_process = self._save_task_to_firestore(task)
            if not should_process:
                return  # Idempotenter Abbruch

            self._delegate_task_to_sda(task)
            self._update_task_after_delegation(doc_ref, task.task_id)

            logging.info(f"Task {task.task_id} erfolgreich verarbeitet.")

        except Exception as e:
            logging.error(f"Fehler bei der Task-Verarbeitung: {e}", exc_info=True)
            raise  # Fehler weiterleiten

    def _save_task_to_firestore(self, task: task_pb2.Task) -> tuple[firestore.DocumentReference, bool]:
        """Speichert den Task in Firestore und prüft auf Idempotenz."""
        try:
            task_dict = json_format.MessageToDict(task)
            doc_ref = self.db.collection("tasks").document(task.task_id)

            task_snapshot = doc_ref.get()
            if task_snapshot.exists and task_snapshot.to_dict().get("assignedToAgentId"):
                logging.warning(f"Task {task.task_id} wurde bereits an {task_snapshot.to_dict().get('assignedToAgentId')} zugewiesen. Breche die Verarbeitung ab.")
                return doc_ref, False

            doc_ref.set(task_dict, merge=True)
            logging.info(f"Task {task.task_id} successfully saved/updated in Firestore.")
            return doc_ref, True
        except Exception as e:
            logging.error(f"Fehler beim Speichern in Firestore: {e}", exc_info=True)
            raise IOError("Firestore write error") from e

    def _delegate_task_to_sda(self, task: task_pb2.Task):
        """Delegiert den Task an den nächsten Agenten via Pub/Sub."""
        if not task.task_id:
            logging.warning("Keine Task-ID vorhanden, Delegation wird übersprungen.")
            return

        logging.info(f"Delegating task {task.task_id} to {self.assigned_agent_id} via topic '{self.delegation_topic}'...")
        try:
            publish_proto_message_as_json(
                publisher=self.publisher,
                project_id=self.project_id,
                topic_id=self.delegation_topic,
                proto_message=task
            )
        except Exception as e:
            logging.error(f"Fehler beim Delegieren des Tasks an Pub/Sub: {e}", exc_info=True)
            raise IOError("Pub/Sub publish error") from e

    def _update_task_after_delegation(self, doc_ref, task_id: str):
        """Aktualisiert den Task-Status in Firestore nach der Delegation."""
        try:
            update_data = {
                "status": task_pb2.TaskStatus.TASK_STATUS_IN_PROGRESS,
                "assignedToAgentId": self.assigned_agent_id,
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            doc_ref.update(update_data)
            logging.info(f"Task {task_id} status updated to IN_PROGRESS and assigned to {self.assigned_agent_id}.")
        except Exception as e:
            logging.error(f"Fehler beim Aktualisieren des Tasks in Firestore: {e}", exc_info=True)
            raise IOError("Firestore update error") from e

```

---


## Directory: `python/services/agent_sda_be`

### `main.py`
```python
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

```

---

### `service.py`
```python
import logging
import time
import uuid

from google.protobuf import json_format
from google.protobuf.timestamp_pb2 import Timestamp

from kiorga.datamodel import final_report_pb2, task_pb2
from kiorga.utils.pubsub_helpers import decode_pubsub_message, publish_proto_message_as_json
from kiorga.utils.validation import parse_and_validate_message


class TaskHandler:
    """
    Kapselt die Geschäftslogik für die Verarbeitung von Tasks durch den SDA-BE-Agenten.
    """

    def __init__(self, db_client, pub_client, project_id: str, agent_id: str, reports_topic: str):
        self.db = db_client
        self.publisher = pub_client
        self.project_id = project_id
        self.agent_id = agent_id
        self.reports_topic = reports_topic

    def handle_task(self, envelope: dict):
        """
        Orchestriert den gesamten Prozess der Task-Verarbeitung.
        """
        task = None
        start_time = time.time()
        try:
            json_string_received, publish_timestamp = decode_pubsub_message(envelope)
            # receive_latency = time.time() - publish_timestamp # Metrik entfernt

            task = parse_and_validate_message(
                json_string=json_string_received,
                message_class=task_pb2.Task
            )
            logging.info(f"SDA-BE received task: id={task.task_id}, title='{task.title}'")

            if self._check_idempotency(task.task_id):
                return

            self._update_task_status(task.task_id, task_pb2.TaskStatus.TASK_STATUS_IN_PROGRESS)
            self._perform_simulated_work(task.task_id)
            self._create_and_publish_final_report(task.task_id)
            self._update_task_status(task.task_id, task_pb2.TaskStatus.TASK_STATUS_COMPLETED)

            processing_time = time.time() - start_time
            logging.info(f"Task {task.task_id} erfolgreich verarbeitet in {processing_time:.4f} Sekunden.")

        except (ValueError, IOError) as e:
            raise e
        except Exception as e:
            logging.error(f"Unerwarteter Fehler bei der Verarbeitung von Task {getattr(task, 'task_id', 'N/A')}: {e}", exc_info=True)
            if task and task.task_id:
                self._update_task_status(task.task_id, task_pb2.TaskStatus.TASK_STATUS_FAILED)
            raise IOError("Unbekannter interner Fehler") from e

    def _check_idempotency(self, task_id: str) -> bool:
        """Prüft, ob bereits ein Abschlussbericht für den Task existiert."""
        reports_ref = self.db.collection("final_reports")
        query = reports_ref.where("taskId", "==", task_id).limit(1)
        if list(query.stream()):
            logging.warning(f"Task {task_id} wurde bereits abgeschlossen. Breche Verarbeitung ab.")
            return True
        return False

    def _update_task_status(self, task_id: str, status: task_pb2.TaskStatus):
        """Aktualisiert den Status eines Tasks in Firestore."""
        try:
            task_doc_ref = self.db.collection("tasks").document(task_id)
            task_doc_ref.update({"status": status})
            logging.info(f"Task {task_id} status updated to {task_pb2.TaskStatus.Name(status)}.")
        except Exception as e:
            logging.error(f"Konnte Task-Status für {task_id} nicht aktualisieren: {e}", exc_info=True)
            # In einem realen Szenario könnte hier ein robusterer Fehler-Handler stehen.

    def _perform_simulated_work(self, task_id: str):
        """Simuliert die eigentliche Arbeit des Agenten."""
        logging.info(f"Starting work on task {task_id}...")
        time.sleep(2)
        logging.info(f"Work on task {task_id} finished.")

    def _create_and_publish_final_report(self, task_id: str):
        """Erstellt, speichert und veröffentlicht einen Abschlussbericht."""
        report_id = str(uuid.uuid4())
        now = Timestamp()
        now.GetCurrentTime()

        final_report = final_report_pb2.FinalReport(
            report_id=report_id,
            task_id=task_id,
            executing_agent_id=self.agent_id,
            final_status=final_report_pb2.FinalStatus.FINAL_STATUS_SUCCESS,
            summary="SDA-BE has successfully completed the simulated task.",
            completion_timestamp=now
        )

        try:
            report_dict = json_format.MessageToDict(final_report)
            self.db.collection("final_reports").document(report_id).set(report_dict)
            logging.info(f"FinalReport {report_id} for task {task_id} saved to Firestore.")

            publish_proto_message_as_json(
                publisher=self.publisher,
                project_id=self.project_id,
                topic_id=self.reports_topic,
                proto_message=final_report
            )
        except Exception as e:
            logging.error(f"Fehler beim Speichern/Veröffentlichen des Berichts für Task {task_id}: {e}", exc_info=True)
            raise IOError("could not persist or publish final report") from e

```

---

