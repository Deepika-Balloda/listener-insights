"""
Shared database connection helper.

Controlled by the DB_BACKEND environment variable, same pattern as
EMBEDDING_BACKEND:
    DB_BACKEND=sqlite     (default) -- connects to the local olt_listener.db file
    DB_BACKEND=azure_sql  -- connects to Azure SQL using the AZURE_SQL_* variables below

Required environment variables when DB_BACKEND=azure_sql:
    AZURE_SQL_SERVER    e.g. your-server.database.windows.net
    AZURE_SQL_DATABASE  e.g. listener-test-db
    AZURE_SQL_USER      e.g. your-admin-login
    AZURE_SQL_PASSWORD  your server admin password
"""

import os
import sqlite3
import pyodbc

DB_BACKEND = os.environ.get("DB_BACKEND", "sqlite")
print(f"DB_BACKEND is set to: {DB_BACKEND}")
DB_PATH = "olt_listener.db"


def get_connection():
    if DB_BACKEND == "azure_sql":
        server = os.environ["AZURE_SQL_SERVER"]
        database = os.environ["AZURE_SQL_DATABASE"]
        username = os.environ["AZURE_SQL_USER"]
        password = os.environ["AZURE_SQL_PASSWORD"]
        conn_str = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=90;"
        )
        return pyodbc.connect(conn_str)
    else:
        return sqlite3.connect(DB_PATH)