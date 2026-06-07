FROM python:3.13-slim

# Umgebungsvariablen für Python Optimierung
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Arbeitsverzeichnis festlegen
WORKDIR /app

# System-Abhängigkeiten installieren (nur einmal während des Builds)
# liblzma ist oft nötig für pandas/numpy in slim-Images
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    liblzma-dev \
    && rm -rf /var/lib/apt/lists/*

# Erst die requirements installieren (nutzt Docker Cache effizienter)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Den Rest des Codes kopieren
COPY . .

# Streamlit Konfiguration (wie in deinem Beispiel)
EXPOSE 8501
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Startbefehl
CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]