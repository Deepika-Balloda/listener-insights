"""
Exports the current SQLite data into CSV files, in the exact shape needed
to bulk-import into Azure SQL once the schema in azure_sql_schema.sql has
been created there (e.g. via Azure Data Studio's "Import Wizard", or the
`bcp` command-line tool).

This is the second half of the migration proof: azure_sql_schema.sql shows
the schema translates cleanly, this script shows the DATA can move too.

Run:
    python export_for_azure_sql.py
"""

import sqlite3
import pandas as pd

DB_PATH = "olt_listener.db"

conn = sqlite3.connect(DB_PATH)

interactions_df = pd.read_sql_query("SELECT * FROM interactions", conn)
interactions_df.to_csv("interactions_export.csv", index=False)
print(f"Exported {len(interactions_df)} rows to interactions_export.csv")

try:
    chat_log_df = pd.read_sql_query("SELECT * FROM chat_log", conn)
    chat_log_df.to_csv("chat_log_export.csv", index=False)
    print(f"Exported {len(chat_log_df)} rows to chat_log_export.csv")
except Exception as e:
    print(f"chat_log export skipped (table may be empty or not yet created): {e}")

conn.close()

print()
print("Next step (once an Azure SQL database exists): run azure_sql_schema.sql")
print("against it, then bulk-import these CSVs using Azure Data Studio's")
print("Import Wizard or the `bcp` command-line tool.")
