"""
Matching debug tool — type a question, see the top-5 closest known
questions and their actual similarity scores. Use this to figure out
a good SIMILARITY_THRESHOLD for app.py, and to spot which intents
your dataset doesn't cover well yet.

Run from your OLT-Listener folder (same place as app.py):
    python test_matching.py
"""

import sqlite3
import pandas as pd
import numpy as np
import ollama

DB_PATH = "olt_listener.db"
EMBED_MODEL = "nomic-embed-text"


def get_embedding(text):
    result = ollama.embeddings(model=EMBED_MODEL, prompt=text)
    return result["embedding"]


def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0


def load_known_questions():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT DISTINCT user_question, chatbot_response, category FROM interactions",
        conn,
    )
    conn.close()

    pairs = []
    print(f"Embedding {len(df)} known questions (one-time cost, this may take a moment)...")
    for _, row in df.iterrows():
        emb = get_embedding(row["user_question"])
        pairs.append((row["user_question"], row["chatbot_response"], row["category"], emb))
    print("Ready.\n")
    return pairs


def top_matches(user_msg, known_pairs, top_n=5):
    q_emb = get_embedding(user_msg)
    scored = []
    for question, answer, category, emb in known_pairs:
        score = cosine_similarity(q_emb, emb)
        scored.append((score, question, answer, category))
    scored.sort(reverse=True)
    return scored[:top_n]


if __name__ == "__main__":
    known_pairs = load_known_questions()
    print("Type a test question (or 'quit' to exit).\n")
    while True:
        msg = input("You: ").strip()
        if msg.lower() in ("quit", "exit"):
            break
        if not msg:
            continue
        matches = top_matches(msg, known_pairs)
        print()
        for score, question, answer, category in matches:
            print(f"  {score:.3f}  [{category}]  {question}")
            print(f"          -> {answer}")
        print()