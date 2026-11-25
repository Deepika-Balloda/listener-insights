import sqlite3
import pandas as pd

# =====================================================================
# 1. LOAD EXCEL DATA & INITIALISE DATABASE
# =====================================================================
excel_file = "listener_synthetic_dataset.xlsx"
db_file = "olt_listener.db"

print("🔄 Reading synthetic dataset from Excel...")
# Read the Excel file into a Python Dataframe
df = pd.read_excel(excel_file)

# Clean up column names by removing spaces and making them lowercase for easy database queries
df.columns = [c.strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns]

print(f"📊 Loaded {len(df)} rows. Setting up SQLite database...")
# Connect to SQLite (this automatically creates the file 'olt_listener.db' if it doesn't exist)
conn = sqlite3.connect(db_file)

# Save the data into a database table called 'interactions'
df.to_sql("interactions", conn, if_exists="replace", index=False)
print("✅ Data successfully saved to SQLite table: 'interactions'")

# =====================================================================
# 2. RUN BASELINE ANALYTICS (The Insights)
# =====================================================================
print("\n🔍 Running Baseline Data Analytics...\n")

# Insight 1: Most Recurring Questions (Exact text matching)
print("--- Insight 1: Top Recurring Questions ---")
top_questions = df["user_question"].value_counts().head(5)
print(top_questions if not top_questions.empty else "No repeated questions found.")
print("-" * 40)

# Insight 2: Response Unresolved Rate
print("\n--- Insight 2: Unresolved Rate by Chatbot Response ---")
if "resolved" in df.columns and "chatbot_response" in df.columns:
    # Group by the chatbot response and calculate how often it results in "No"
    unresolved_summary = df.groupby("chatbot_response")["resolved"].apply(
        lambda x: (x.astype(str).str.strip().str.lower() == "no").sum() / len(x) * 100
    ).sort_values(ascending=False).head(5)
    for resp, rate in unresolved_summary.items():
        print(f"Response: '{resp[:50]}...' -> Unresolved Rate: {rate:.1f}%")
else:
    print("⚠️ 'resolved' or 'chatbot_response' column missing or named differently.")
print("-" * 40)

# Insight 3: Chatbot Loop Detection
print("\n--- Insight 3: Conversations with Multiple Follow-ups (Potential Loops) ---")
if "session_id" in df.columns:
    # Count how many rows exist per Session ID. More rows = more back-and-forth loops.
    session_counts = df["session_id"].value_counts()
    looping_sessions = session_counts[session_counts > 1]
    print(f"Found {len(looping_sessions)} sessions with multiple interactions.")
    if not looping_sessions.empty:
        print("Top looping Session IDs and their message counts:")
        print(looping_sessions.head(5))
else:
    print("⚠️ 'session_id' column missing or named differently.")
print("-" * 40)

# Close the database connection safely when done
conn.close()
print("\n🎉 Baseline analytics run complete! Pipeline is ready.")