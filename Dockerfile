# Listener — Python analysis & insights service
#
# Builds a standalone container for app.py, meant to run alongside the
# .NET Aspire front-end and be called via its HTTP API (dashboard routes
# and /chat), rather than being rewritten in .NET.
#
# Build:
#   docker build -t listener-python .

FROM python:3.11-slim

WORKDIR /app

# Install system-level ODBC dependencies needed for Azure SQL connections
# via pyodbc (the Python package alone isn't enough -- it needs the actual
# ODBC driver manager and Microsoft's SQL Server driver installed at the
# OS level inside this container).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gnupg \
        unixodbc \
        unixodbc-dev \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl -sSL https://packages.microsoft.com/config/debian/12/prod.list | sed 's/\[arch=amd64,armhf,arm64\]/[arch=amd64,armhf,arm64 signed-by=\/usr\/share\/keyrings\/microsoft-prod.gpg]/' > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first, separately from app code, so Docker can
# cache this layer and skip reinstalling on every code change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code, dataset, and templates
COPY app.py .
COPY db_connection.py .
COPY load_dataset.py .
COPY semantic_analysis.py .
COPY templates/ templates/
COPY OLT_Listener_Synthetic_Dataset_v3.xlsx .

# Build the SQLite database at image build time, so the container starts
# with data already loaded (no extra manual step needed after `docker run`).
RUN python load_dataset.py

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]