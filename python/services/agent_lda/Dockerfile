# ===== STAGE 1: Builder =====
# Diese Stage dient dazu, die Python-Abhängigkeiten zu installieren.
FROM python:3.12.3 as builder

# Setze das Arbeitsverzeichnis
WORKDIR /app

# Installiere nur die Abhängigkeiten. Durch das Kopieren der requirements.txt
# und die Installation vor dem Kopieren des restlichen Codes nutzen wir das Docker-Layer-Caching.
COPY python/requirements.txt .
COPY python/services/agent_lda/requirements.txt ./services/agent_lda/requirements.txt

# Erstelle ein virtuelles Environment und installiere die Pakete dorthin.
# Dies isoliert die Abhängigkeiten und macht es einfach, sie in die nächste Stage zu kopieren.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir -r services/agent_lda/requirements.txt

# ===== STAGE 2: Final =====
# Diese Stage erstellt das finale, schlanke Image.
FROM python:3.12.3-slim

# Setze das Arbeitsverzeichnis
WORKDIR /app

# Kopiere das virtuelle Environment aus der Builder-Stage.
COPY --from=builder /opt/venv /opt/venv

# Kopiere den Anwendungs-Code.
# Wir kopieren das kiorga-Paket und den Service-Code.
COPY python/kiorga ./kiorga
COPY python/services/agent_lda/ ./services/agent_lda/

# Aktiviere das virtuelle Environment für alle nachfolgenden Befehle.
ENV PATH="/opt/venv/bin:$PATH"

# Setze den Startbefehl für den Container.
# Wir wechseln in das Service-Verzeichnis, bevor wir den Server starten.
ENV PYTHONPATH="/app:$PYTHONPATH"

# Setze den Startbefehl für den Container.
WORKDIR /app/services/agent_lda
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
