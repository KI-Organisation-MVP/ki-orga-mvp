# ===== STAGE 1: Builder =====
# Diese Stage dient dazu, die Python-Abhängigkeiten zu installieren.
FROM python:3.12.3 as builder

# Setze das Arbeitsverzeichnis
WORKDIR /app

# Installiere nur die Abhängigkeiten. Durch das Kopieren der requirements.txt
# und die Installation vor dem Kopieren des restlichen Codes nutzen wir das Docker-Layer-Caching.
COPY python/requirements.txt .
COPY python/services/agent-sda-be/requirements.txt ./services/agent-sda-be/requirements.txt

# Erstelle ein virtuelles Environment und installiere die Pakete dorthin.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir -r services/agent-sda-be/requirements.txt

# ===== STAGE 2: Final =====
# Diese Stage erstellt das finale, schlanke Image.
FROM python:3.12.3-slim

# Setze das Arbeitsverzeichnis
WORKDIR /app

# Kopiere das virtuelle Environment aus der Builder-Stage.
COPY --from=builder /opt/venv /opt/venv

# Kopiere den Anwendungs-Code.
COPY python/kiorga ./kiorga
COPY python/services/agent-sda-be/ ./services/agent-sda-be/

# Aktiviere das virtuelle Environment für alle nachfolgenden Befehle.
ENV PATH="/opt/venv/bin:$PATH"

# Setze den Startbefehl für den Container.
ENV PYTHONPATH="/app:$PYTHONPATH"

# Setze den Startbefehl für den Container.
WORKDIR /app/services/agent-sda-be
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
