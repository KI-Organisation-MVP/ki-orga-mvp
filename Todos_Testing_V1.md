### 1. Unit-Tests (Testen einzelner "Bauteile")

* **Zweck:** Testen von kleinen, isolierten Logik-Einheiten (z.B. eine einzelne Funktion in `main.py`), ohne dabei von externen Diensten wie Firestore oder Pub/Sub abhängig zu sein.
* **Framework:** **`pytest`**. Das ist der De-facto-Standard in der Python-Community. Es ist deutlich schlanker und mächtiger als das eingebaute `unittest`-Framework.
* **Technologien:**
    * **`pytest`**: Für die Test-Struktur, das Ausführen und die Assertions.
    * **`unittest.mock`**: Eine in Python eingebaute Bibliothek, um externe Abhängigkeiten (wie den Firestore-Client oder den Pub/Sub-Publisher) durch "Test-Dummies" (Mocks) zu ersetzen. Damit können wir prüfen, ob z.B. `db.collection("...").document("...")` mit den korrekten Werten aufgerufen wird, ohne wirklich in eine Datenbank zu schreiben.

---
### 2. Integrationstests (Testen des Zusammenspiels)

* **Zweck:** Testen, wie unser Service mit den echten Google-Cloud-Diensten interagiert. Funktioniert die Verbindung zu Firestore? Ist das Pub/Sub-Nachrichtenformat korrekt?
* **Framework:** Hier verwenden wir ebenfalls **`pytest`**.
* **Technologien:**
    * **Google Cloud Emulators:** Das ist der entscheidende Punkt. Anstatt gegen eine echte, kostenpflichtige Firestore- und Pub/Sub-Instanz zu testen, stellt Google lokale **Emulatoren** zur Verfügung. Das sind kleine Programme, die sich exakt wie die echten Dienste verhalten, aber lokal und im Speicher laufen. Sie sind extrem schnell und kostenlos.
    * Wir würden unsere Test-Pipeline so konfigurieren, dass sie vor den Tests die Emulatoren startet, unseren Agenten-Code damit verbindet und nach den Tests wieder herunterfährt.

---
### 3. End-to-End-Tests (Testen der gesamten Kette)

* **Zweck:** Validieren des kompletten Business-Prozesses, genau wie wir es gerade manuell machen.
* **Framework:** Ein **eigenes Test-Skript**, das in Python geschrieben ist.
* **Technologien:**
    * **Unser `create_and_publish_task.py`** ist bereits die Grundlage für einen solchen Test.
    * Wir würden es so erweitern, dass es nach dem Senden der Nachricht in einer Schleife die **Firestore-Datenbank abfragt** und prüft, ob der `Task` nach einer bestimmten Zeit den erwarteten finalen Status (z.B. `IN_PROGRESS` und zugewiesen an `agent-sda-be`) erreicht.
    * Dieser Test würde als letzter Schritt in unserer CI/CD-Pipeline laufen, nachdem die Services auf einer Test-Umgebung deployed wurden.

---
**Zusammenfassend als Empfehlung:**

| Test-Ebene | Primäres Framework | Schlüssel-Technologien |
| :--- | :--- | :--- |
| **Unit-Tests** | `pytest` | `unittest.mock` |
| **Integrationstests** | `pytest` | Firestore & Pub/Sub Emulators |
| **End-to-End-Tests**| Custom Python Script | Google Cloud Client Libraries (Pub/Sub, Firestore) |

Dieser Mix gibt uns schnelles Feedback auf der untersten Ebene (Unit-Tests) und das Vertrauen, dass das Gesamtsystem auf den höheren Ebenen wie erwartet funktioniert.

---
### **Umsetzungsplan zur Einführung von Tests**

  Ziel: Eine solide Testbasis schaffen, die als Vorlage für alle anderen Services dient.

  #### **1. Implementierung der Unit-Tests (Testen einzelner "Bauteile")**

  ##### Schritt 1: Test-Infrastruktur aufsetzen


   1. Wir fügen pytest und pytest-mock zu den Entwicklungsabhängigkeiten hinzu. Da
      wir keine separate requirements-dev.txt haben, fügen wir sie direkt zur
      requirements.txt des agent_lda hinzu.
   2. Wir erstellen die notwendige Verzeichnisstruktur für die Tests.


  #### Schritt 2: Erster Unit-Test für den `agent_lda`


   1. Wir beginnen mit dem TaskProcessor in agent_lda, da wir dort die Kernlogik
      bereits sauber vom FastAPI-Framework getrennt haben. Das ist der ideale
      Kandidat für einen Unit-Test.
   2. Wir erstellen eine Testdatei services/agent_lda/tests/test_service.py.
   3. In dieser Datei testen wir die process_task-Methode des TaskProcessor.
       * Szenario 1 (Happy Path): Der Service erhält einen validen Task und
         verarbeitet ihn korrekt.
       * Mocking: Dabei werden wir die Interaktion mit externen Systemen (z.B. der
         Pub/Sub-Client zum Veröffentlichen der nächsten Nachricht) mit pytest-mock
         mocken. Der Test prüft dann, ob unsere Logik versucht hat, die korrekte
         Nachricht mit den korrekten Daten zu senden, ohne sie tatsächlich zu
         senden.
       * Szenario 2 (Sad Path): Der Service erhält einen invaliden Task (z.B.
         fehlende Daten) und wir prüfen, ob er wie erwartet einen Fehler auslöst
         oder eine Fehlermetrik sendet.

  #### Schritt 3: CI-Pipeline erweitern


   1. Wir fügen einen neuen Schritt zur cloudbuild-pr.yaml hinzu.
   2. Dieser Schritt führt pytest für den agent_lda Service aus. Dadurch stellen wir
      sicher, dass keine Pull Requests gemerged werden können, die bestehende Tests
      brechen.


  ### **TODO: 2. Implementierung Integrationstests (Testen des Zusammenspiels)**

  ### **TODO: 3. End-to-End-Tests (Testen der gesamten Kette)**

  