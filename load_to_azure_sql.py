import os
import pandas as pd
import pyodbc

server = os.environ["AZURE_SQL_SERVER"]
database = os.environ["AZURE_SQL_DATABASE"]
username = os.environ["AZURE_SQL_USER"]
password = os.environ["AZURE_SQL_PASSWORD"]

conn_str = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER={server},1433;DATABASE={database};"
    f"UID={username};PWD={{{password}}};"
    "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
)

conn = pyodbc.connect(conn_str)
cur = conn.cursor()
cur.fast_executemany = True


def load(table, csv_file, columns):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    existing = cur.fetchone()[0]
    if existing > 0:
        print(f"{table}: already has {existing} rows, skipping to avoid duplicates")
        return
    df = pd.read_csv(csv_file, dtype=str)
    df = df[columns]
    df = df.astype(object).where(df.notna(), None)
    if df.empty:
        print(f"{table}: CSV is empty, nothing to load")
        return
    col_list = ", ".join(f"[{c}]" for c in columns)
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
    cur.executemany(sql, df.values.tolist())
    conn.commit()
    print(f"{table}: loaded {len(df)} rows")


load(
    "interactions",
    "interactions_export.csv",
    ["session_id", "timestamp", "user_question", "chatbot_response",
     "follow_up_question", "resolved", "category", "channel", "customer_id"],
)

load(
    "chat_log",
    "chat_log_export.csv",
    ["timestamp", "question", "classification", "response"],
)

conn.close()
print("Done")