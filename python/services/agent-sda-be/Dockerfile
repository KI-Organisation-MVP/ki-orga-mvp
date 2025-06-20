# Verwende ein offizielles, schlankes Python-Image als Basis
FROM python:3.12-slim

# Setze das Arbeitsverzeichnis im Container
WORKDIR /app

# Kopiere den GESAMTEN Inhalt unseres python-Verzeichnisses in den Container.
COPY python/ .

# Installiere die Python-Abhängigkeiten aus der korrekten requirements.txt
RUN pip install --no-cache-dir -r services/agent-sda-be/requirements.txt

# NEUER DIAGNOSE-SCHRITT: Gib alle installierten Pakete und ihre Versionen im Build-Log aus
RUN pip freeze

# Kopiere den Rest des Codes
COPY python/services/agent-sda-fe/ .

# Starte den Gunicorn-Server für diesen spezifischen Service
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--chdir", "services/agent-sda-be", "main:app"]