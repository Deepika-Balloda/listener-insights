"""
Reloads the interactions table in olt_listener.db from the v3 synthetic
dataset, which adds Channel and Customer_ID to the v2 (2000-record) set.

Run this once from your project folder:
    python load_dataset.py
"""

import pandas as pd
import sqlite3

XLSX_PATH = "OLT_Listener_Synthetic_Dataset_v3.xlsx"
DB_PATH = "olt_listener.db"

df = pd.read_excel(XLSX_PATH)

df = df.rename(columns={
    "Session ID": "session_id",
    "Timestamp": "timestamp",
    "User Question": "user_question",
    "Chatbot Response": "chatbot_response",
    "Follow-up Question": "follow_up_question",
    "Resolved": "resolved",
    "Category": "category",
    "Channel": "channel",
    "Customer_ID": "customer_id",
})

conn = sqlite3.connect(DB_PATH)
df.to_sql("interactions", conn, if_exists="replace", index=False)
conn.close()

print(f"Loaded {len(df)} records into '{DB_PATH}' (interactions table).")
print(f"Unique questions: {df['user_question'].nunique()}")