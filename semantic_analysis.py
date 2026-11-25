import sqlite3
import json
import pandas as pd
import ollama
import numpy as np

# Connect to our local database
db_file = "olt_listener.db"
conn = sqlite3.connect(db_file)

print("🔄 Fetching unique questions from SQLite database...")
df = pd.read_sql_query("SELECT DISTINCT user_question FROM interactions", conn)
conn.close()

questions = df["user_question"].dropna().tolist()
print(f"🧠 Found {len(questions)} unique questions. Generating AI mathematical vectors...")

# Dictionary to store the numerical meaning (embeddings) of each sentence
embeddings = []

# Ask Ollama to translate each sentence into numerical vectors
for q in questions:
    response = ollama.embeddings(model="nomic-embed-text", prompt=q)
    embeddings.append(response["embedding"])

print("✅ AI Vector generation complete! Grouping similar meanings together...\n")


# Simple semantic matching function
def calculate_similarity(vec1, vec2):
    # Calculates how mathematically close two meaning-vectors are
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))


# Track which questions have already been grouped
grouped = set()

# This is the new part: instead of only printing, we also build a list
# of clusters that we can save to a file for the dashboard to read later.
clusters_for_dashboard = []

print("--- AI Semantic Grouping Report ---")
for i, q1 in enumerate(questions):
    if q1 in grouped:
        continue

    # Start a new semantic cluster/group
    cluster = [q1]
    grouped.add(q1)

    for j, q2 in enumerate(questions):
        if q2 not in grouped:
            # Check if the AI thinks the meaning similarity is higher than 75%
            similarity = calculate_similarity(embeddings[i], embeddings[j])
            if similarity > 0.75:
                cluster.append(q2)
                grouped.add(q2)

    # Print the group if the AI found variations or reworded matches
    if len(cluster) > 1:
        print(f"\n🤖 Found Cluster (Core Intent: '{cluster[0][:40]}...')")
        for item in cluster:
            print(f"  ↳ Match: \"{item}\"")

        # Save this cluster for the dashboard too
        clusters_for_dashboard.append({
            "core_intent": cluster[0],
            "matches": cluster,
        })

# Save all clusters to a JSON file the dashboard can read instantly
with open("semantic_clusters.json", "w") as f:
    json.dump(clusters_for_dashboard, f, indent=2)

print(f"\n💾 Saved {len(clusters_for_dashboard)} clusters to semantic_clusters.json")
print("🎉 Semantic analysis complete! Your AI layer is running.")