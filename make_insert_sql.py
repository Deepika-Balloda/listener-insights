import pandas as pd

CHUNK = 500


def txt(v, required=False):
    if pd.isna(v) or str(v) == "":
        return "N''" if required else "NULL"
    return "N'" + str(v).replace("'", "''") + "'"


def build(table, csv_file, columns, required, out):
    df = pd.read_csv(csv_file, dtype=str)[columns]
    ts = pd.Series([pd.to_datetime(x, errors="coerce") for x in df["timestamp"]])
    if ts.isna().any():
        raise SystemExit(f"{table}: {int(ts.isna().sum())} bad timestamps, stopping")
    col_list = ", ".join(f"[{c}]" for c in columns)
    out.append(f"IF (SELECT COUNT(*) FROM {table}) = 0\nBEGIN")
    for start in range(0, len(df), CHUNK):
        rows = []
        for i in range(start, min(start + CHUNK, len(df))):
            vals = []
            for c in columns:
                if c == "timestamp":
                    vals.append("'" + ts.iloc[i].strftime("%Y-%m-%d %H:%M:%S.%f") + "'")
                else:
                    vals.append(txt(df.iloc[i][c], c in required))
            rows.append("(" + ", ".join(vals) + ")")
        out.append(f"INSERT INTO {table} ({col_list}) VALUES\n" + ",\n".join(rows) + ";")
    out.append("END\n")
    print(f"{table}: {len(df)} rows prepared")


out = ["SET NOCOUNT ON;\n"]

build(
    "interactions",
    "interactions_export.csv",
    ["session_id", "timestamp", "user_question", "chatbot_response",
     "follow_up_question", "resolved", "category", "channel", "customer_id"],
    {"session_id", "user_question", "chatbot_response"},
    out,
)

build(
    "chat_log",
    "chat_log_export.csv",
    ["timestamp", "question", "classification", "response"],
    {"question", "classification", "response"},
    out,
)

out.append(
    "SELECT 'interactions' AS table_name, COUNT(*) AS total_rows FROM interactions\n"
    "UNION ALL\n"
    "SELECT 'chat_log', COUNT(*) FROM chat_log;"
)

with open("load_data.sql", "w", encoding="utf-8") as f:
    f.write("\n".join(out))

print("Created load_data.sql")