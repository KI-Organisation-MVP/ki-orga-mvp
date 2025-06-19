# Verwende ein offizielles, schlankes Python-Image als Basis
FROM python:3.12-slim

# Setze das Arbeitsverzeichnis im Container
WORKDIR /app

# Kopiere den GESAMTEN Inhalt unseres python-Verzeichnisses in den Container.
# Dadurch haben wir jetzt /app/kiorga/ und /app/services/ im Container.
COPY python/ .

# Installiere die Python-Abhängigkeiten aus der korrekten requirements.txt
RUN pip install --no-cache-dir -r services/agent-lda/requirements.txt

# Starte den Gunicorn-Server.
# Wir sagen ihm, er soll das Arbeitsverzeichnis auf den Ordner unseres Services setzen.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--chdir", "services/agent-lda", "main:app"]