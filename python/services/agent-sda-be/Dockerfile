# Wir verwenden ein offizielles, schlankes Python-Image als Basis
FROM python:3.12-slim

# Wir setzen das Arbeitsverzeichnis im Container auf /app
WORKDIR /app

# Kopiere die "Einkaufsliste" und installiere die Python-Bibliotheken
COPY python/services/agent-sda-be/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiere den Rest unseres Anwendungs-Codes (also main.py etc.)
COPY python/services/agent-sda-be/ .

# Dieser Befehl wird ausgeführt, wenn der Container startet.
# Er startet einen robusten Webserver (gunicorn), der unsere App (main:app) ausführt.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "main:app"]