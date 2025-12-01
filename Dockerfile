FROM python:3.12-slim

# System-Updates + minimale Tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis
WORKDIR /app

# Requirements zuerst kopieren (Layer-Caching)
COPY requirements.txt .

# Dependencies installieren
RUN pip install --no-cache-dir -r requirements.txt

# App-Code kopieren
COPY . .

# Streamlit-Konfiguration: im Docker-Umfeld wird das per CLI geregelt.
# Startkommando: Streamlit auf dem von Vercel gesetzten $PORT starten
CMD ["sh", "-c", "streamlit run app.py --server.port $PORT --server.address 0.0.0.0"]
