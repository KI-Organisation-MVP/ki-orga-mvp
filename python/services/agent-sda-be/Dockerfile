# Verwende ein offizielles, schlankes Python-Image als Basis
FROM python:3.12-slim

# Setze das Arbeitsverzeichnis im Container
WORKDIR /app

# Kopiere den GESAMTEN Inhalt unseres python-Verzeichnisses in den Container.
COPY python/ .

# Installiere die Python-Abhängigkeiten aus der korrekten requirements.txt
RUN pip install --no-cache-dir -r services/agent-sda-be/requirements.txt

# Starte den Gunicorn-Server für diesen spezifischen Service
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--chdir", "services/agent-sda-be", "main:app"]