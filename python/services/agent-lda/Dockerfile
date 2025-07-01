# Verwende ein offizielles, schlankes Python-Image als Basis
FROM python:3.12.3

# Setze das Arbeitsverzeichnis im Container
WORKDIR /app

# Kopiere den GESAMTEN Inhalt unseres python-Verzeichnisses in den Container.
# Dadurch haben wir jetzt /app/kiorga/ und /app/services/ im Container.
COPY python/ .

# Installiere die Python-Abhängigkeiten
RUN pip install --no-cache-dir -r services/agent-lda/requirements.txt

# NEUER DIAGNOSE-SCHRITT: Gib alle installierten Pakete und ihre Versionen im Build-Log aus
RUN pip freeze

# Kopiere den Rest des Codes
COPY python/services/agent-lda/ .

# Starte den Gunicorn-Server.
# Wir sagen ihm, er soll das Arbeitsverzeichnis auf den Ordner unseres Services setzen.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]