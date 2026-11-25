"""
Listener Insights Dashboard + Live Chat (separate page) + live-updating stats

Routes:
  /            - the dashboard (server-rendered on load)
  /stats       - JSON version of the same dashboard numbers, polled by
                 the page's JavaScript every 20s to refresh without a
                 full reload
  /chat-page   - the standalone chat interface page
  /chat        - POST endpoint the chat page talks to

Requires: pip install ollama
(Ollama must be running locally with the nomic-embed-text model pulled:
    ollama pull nomic-embed-text)
"""

import random
import re
from flask import Flask, render_template, request, jsonify

import json
import os
import pandas as pd
import numpy as np
from datetime import datetime
import ollama

app = Flask(__name__)

DB_PATH = "olt_listener.db"
CLUSTERS_PATH = "semantic_clusters.json"
EMBED_MODEL = "nomic-embed-text"
SIMILARITY_THRESHOLD = 0.70

# ---------------------------------------------------------------------------
# Embedding backend switch, same pattern as the existing GENERATION_BACKEND
# idea for llm_backend.py: local dev keeps using Ollama (free, no external
# dependency); production points at Azure OpenAI embeddings instead, to
# match the org's existing Azure environment and avoid having to host and
# maintain a model server ourselves.
#
#   EMBEDDING_BACKEND=ollama        (default) -- calls local Ollama
#   EMBEDDING_BACKEND=azure_openai  -- calls Azure OpenAI embeddings API
#
# Azure OpenAI requires three more env vars when selected:
#   AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_EMBEDDING_DEPLOYMENT
# ---------------------------------------------------------------------------
EMBEDDING_BACKEND = os.environ.get("EMBEDDING_BACKEND", "ollama")

# ---------------------------------------------------------------------------
# Free-text safety: two separate concerns, handled differently.
#
# 1. Inappropriate content (abusive/harmful language) -- we decline politely
#    and log it as "flagged_inappropriate" so the team can see how often
#    this happens, but we still store what was actually typed (useful for
#    understanding the pattern).
#
# 2. Sensitive data accidentally typed into the box (card numbers, national
#    ID numbers) -- this is a data-ethics concern, not a moderation one. We
#    never store the raw text in this case; see redact_sensitive() and the
#    "Data-ethics" note in README.md.
# ---------------------------------------------------------------------------

# Small, generic starter list -- flag on word boundaries, case-insensitive.
# Intentionally conservative (a short list of clearly abusive/harmful terms)
# to avoid false positives on legitimate frustrated customers ("this is
# broken", "I'm so annoyed" should NOT be flagged).
INAPPROPRIATE_TERMS = {
    "idiot", "stupid", "dumb", "useless", "shut up",
    "kill yourself", "f*** you", "screw you",
}

MODERATION_REPLY = (
    "I want to help, but I can't continue if the conversation includes "
    "language like that. If you'd like, please rephrase and I'll do my "
    "best to assist, or ask to speak with a member of the support team."
)

# Patterns for data that should never be stored, even if a user pastes it
# in by mistake. Kept deliberately narrow (clear formats only) so we don't
# over-redact ordinary text.
SENSITIVE_DATA_PATTERNS = [
    re.compile(r"\b(?:\d[ -]*?){13,16}\b"),          # card-number-like digit runs
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),             # SSN-style xxx-xx-xxxx
]


def contains_inappropriate_content(text):
    lowered = text.lower()
    return any(term in lowered for term in INAPPROPRIATE_TERMS)


def redact_sensitive(text):
    """Replaces anything matching a sensitive-data pattern with a
    placeholder, so it never reaches the database. Returns
    (redacted_text, was_redacted)."""
    redacted = text
    was_redacted = False
    for pattern in SENSITIVE_DATA_PATTERNS:
        if pattern.search(redacted):
            redacted = pattern.sub("[redacted]", redacted)
            was_redacted = True
    return redacted, was_redacted

# Words that signal opposite intents. If the user's message uses a word
# from one side and the best-matching KNOWN QUESTION uses a word from
# the other side, treat it as a mismatch even if the similarity score
# is high -- the embedding model cannot tell "cancel" from "take" apart
# on its own.
OPPOSITE_ACTION_PAIRS = [
    ({"cancel", "close", "downgrade", "remove", "stop", "disable"},
     {"add", "sign", "subscribe", "enable", "upgrade", "get", "take"}),
]

# Small-talk detection: greetings, thanks, goodbyes, acknowledgements
GREETINGS = {
    "hi", "hello", "hey", "hii", "heya", "hiya", "yo",
    "good morning", "good afternoon", "good evening", "greetings",
}
THANKS_WORDS = {"thanks", "thank you", "thankyou", "thx", "cheers", "appreciate it"}
GOODBYE_WORDS = {"bye", "goodbye", "see you", "later", "cya"}
ACK_WORDS = {"ok", "okay", "kk", "cool", "alright", "got it", "sure"}

GREETING_REPLIES = [
    "Hey! How can I help you today?",
    "Hi there! What can I do for you?",
    "Hello! What are you looking for help with?",
]
THANKS_REPLIES = [
    "You're welcome! Let me know if there's anything else.",
    "No problem at all — happy to help!",
    "Glad I could help. Anything else you need?",
]
GOODBYE_REPLIES = [
    "Take care! Feel free to come back anytime.",
    "Bye for now — reach out if you need anything else.",
    "See you next time!",
]
ACK_REPLIES = [
    "Got it, thanks for confirming!",
    "Understood!",
    "Noted, thanks!",
]
FALLBACK_REPLIES = [
    "Hmm, I'm not quite sure about that one. I can help with things like password resets, billing, API keys, or account access — does one of those match what you need?",
    "I don't have a good answer for that yet, sorry! Try asking about password resets, billing, API keys, or account access, and I'll do my best.",
    "That one's a bit outside what I can help with right now. I'm best with password resets, billing, API keys, or account access — is it related to any of those?",
]

_known_question_cache = None


from db_connection import get_connection, DB_BACKEND


def load_semantic_clusters():
    if os.path.exists(CLUSTERS_PATH):
        with open(CLUSTERS_PATH) as f:
            return json.load(f)
    return []


def compute_dashboard_data():
    """All the dashboard numbers, in one place, so both '/' and '/stats'
    use the exact same logic and never drift apart."""
    conn = get_connection()

    if DB_BACKEND == "azure_sql":
        top_questions_df = pd.read_sql_query(
            """
            SELECT TOP 5 user_question, COUNT(*) AS times_asked
            FROM interactions
            GROUP BY user_question
            ORDER BY times_asked DESC
            """,
            conn,
        )
    else:
        top_questions_df = pd.read_sql_query(
            """
            SELECT user_question, COUNT(*) AS times_asked
            FROM interactions
            GROUP BY user_question
            ORDER BY times_asked DESC
            LIMIT 5
            """,
            conn,
        )

    resolution_df = pd.read_sql_query(
        "SELECT resolved, COUNT(*) AS count FROM interactions GROUP BY resolved",
        conn,
    )
    total = int(resolution_df["count"].sum())

    def count_for(value):
        match = resolution_df.loc[resolution_df["resolved"].str.lower() == value, "count"]
        return int(match.sum()) if not match.empty else 0

    unresolved = count_for("no")
    unclear = count_for("unclear")
    resolved = count_for("yes")

    unresolved_rate = round((unresolved / total) * 100, 1) if total > 0 else 0
    unclear_rate = round((unclear / total) * 100, 1) if total > 0 else 0
    resolved_rate = round((resolved / total) * 100, 1) if total > 0 else 0

    if DB_BACKEND == "azure_sql":
        looping_df = pd.read_sql_query(
            """
            SELECT TOP 5 session_id, COUNT(*) AS follow_up_count
            FROM interactions
            WHERE follow_up_question IS NOT NULL AND follow_up_question != ''
            GROUP BY session_id
            ORDER BY follow_up_count DESC
            """,
            conn,
        )
    else:
        looping_df = pd.read_sql_query(
            """
            SELECT session_id, COUNT(*) AS follow_up_count
            FROM interactions
            WHERE follow_up_question IS NOT NULL AND follow_up_question != ''
            GROUP BY session_id
            ORDER BY follow_up_count DESC
            LIMIT 5
            """,
            conn,
        )

    worst_df = pd.read_sql_query(
        """
        SELECT chatbot_response,
               COUNT(*) AS total_uses,
               SUM(CASE WHEN LOWER(TRIM(resolved)) = 'no' THEN 1 ELSE 0 END) AS unresolved_count
        FROM interactions
        GROUP BY chatbot_response
        """,
        conn,
    )
    worst_df["unresolved_rate"] = (
        (worst_df["unresolved_count"] / worst_df["total_uses"]) * 100
    ).round(1)
    worst_df = worst_df.sort_values("unresolved_rate", ascending=False).head(5)
    worst_df["chatbot_response_short"] = worst_df["chatbot_response"].str.slice(0, 60) + "..."

    # Coverage by OLT product area -- shows how many unique questions and
    # total interactions fall under each real OLT product (MVC, Insights,
    # Plant, Platform Administration, Plant Partner Integration, and the
    # deliberately out-of-scope bucket). Traceable straight from the
    # 'category' column, same evidence-based approach as every other block.
    coverage_df = pd.read_sql_query(
        """
        SELECT category,
               COUNT(DISTINCT user_question) AS unique_questions,
               COUNT(*) AS total_interactions
        FROM interactions
        GROUP BY category
        ORDER BY total_interactions DESC
        """,
        conn,
    )

    # Live chat activity, from the chat_log table (created the first time
    # someone uses the chat). Included so the dashboard reflects real
    # usage, not just the original synthetic dataset.
    try:
        chat_conn = get_connection()
        chat_summary_df = pd.read_sql_query(
            "SELECT classification, COUNT(*) AS count FROM chat_log GROUP BY classification",
            chat_conn,
        )
        chat_conn.close()
        chat_summary = {
            row["classification"]: int(row["count"])
            for _, row in chat_summary_df.iterrows()
        }
    except Exception:
        chat_summary = {}

    # Customers with repeat, unresolved issues -- only meaningful for
    # customers we've seen more than once. Anonymised synthetic
    # Customer_ID only, no real identity involved.
    if DB_BACKEND == "azure_sql":
        repeat_customers_df = pd.read_sql_query(
            """
            SELECT TOP 5 customer_id,
                   COUNT(*) AS total_sessions,
                   SUM(CASE WHEN LOWER(LTRIM(RTRIM(resolved))) = 'no' THEN 1 ELSE 0 END) AS unresolved_sessions
            FROM interactions
            WHERE customer_id IS NOT NULL
            GROUP BY customer_id
            HAVING COUNT(*) > 1
            ORDER BY unresolved_sessions DESC, total_sessions DESC
            """,
            conn,
        )
    else:
        repeat_customers_df = pd.read_sql_query(
            """
            SELECT customer_id,
                   COUNT(*) AS total_sessions,
                   SUM(CASE WHEN LOWER(TRIM(resolved)) = 'no' THEN 1 ELSE 0 END) AS unresolved_sessions
            FROM interactions
            WHERE customer_id IS NOT NULL
            GROUP BY customer_id
            HAVING total_sessions > 1
            ORDER BY unresolved_sessions DESC, total_sessions DESC
            LIMIT 5
            """,
            conn,
        )

    # Breakdown by channel. All current data is "Chat" -- this becomes
    # meaningful once email/call adapters start feeding real records in.
    channel_df = pd.read_sql_query(
        """
        SELECT channel, COUNT(*) AS total_interactions
        FROM interactions
        WHERE channel IS NOT NULL
        GROUP BY channel
        ORDER BY total_interactions DESC
        """,
        conn,
    )

    conn.close()

    return {
        "top_questions": top_questions_df.to_dict(orient="records"),
        "unresolved_rate": unresolved_rate,
        "unclear_rate": unclear_rate,
        "resolved_rate": resolved_rate,
        "total_interactions": total,
        "looping_sessions": looping_df.to_dict(orient="records"),
        "worst_responses": worst_df.to_dict(orient="records"),
        "category_coverage": coverage_df.to_dict(orient="records"),
        "semantic_clusters": load_semantic_clusters(),
        "chat_activity": chat_summary,
        "repeat_customers": repeat_customers_df.to_dict(orient="records"),
        "channel_breakdown": channel_df.to_dict(orient="records"),
    }


@app.route("/")
def dashboard():
    return render_template("index.html", **compute_dashboard_data())


@app.route("/stats")
def stats():
    return jsonify(compute_dashboard_data())


# ---------------------------------------------------------------------------
# Chat (separate page)
# ---------------------------------------------------------------------------

@app.route("/chat-page")
def chat_page():
    return render_template("chat_interface.html")


def _get_embedding_ollama(text):
    result = ollama.embeddings(model=EMBED_MODEL, prompt=text)
    return result["embedding"]


def _get_embedding_azure_openai(text):
    # Imported here, not at module level, so Ollama-only setups (like a
    # plain local dev machine) never need the azure-openai package installed.
    from openai import AzureOpenAI

    client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version="2024-02-01",
    )
    deployment = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]
    result = client.embeddings.create(input=text, model=deployment)
    return result.data[0].embedding


def get_embedding(text):
    if EMBEDDING_BACKEND == "azure_openai":
        return _get_embedding_azure_openai(text)
    return _get_embedding_ollama(text)


def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0


def load_known_questions():
    global _known_question_cache
    if _known_question_cache is not None:
        return _known_question_cache

    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT DISTINCT user_question, chatbot_response FROM interactions", conn
    )
    conn.close()

    pairs = []
    for _, row in df.iterrows():
        emb = get_embedding(row["user_question"])
        pairs.append((row["user_question"], row["chatbot_response"], emb))

    _known_question_cache = pairs
    return pairs


def is_too_short_or_vague(text):
    return len(text.strip().split()) <= 2


def classify_small_talk(text):
    cleaned = text.strip().lower().rstrip("!.,? ")
    if cleaned in GREETINGS:
        return "greeting"
    if cleaned in THANKS_WORDS:
        return "thanks"
    if cleaned in GOODBYE_WORDS:
        return "goodbye"
    if cleaned in ACK_WORDS:
        return "acknowledgement"
    return None


def is_opposite_action(user_msg, matched_question):
    user_words = set(user_msg.lower().split())
    matched_words = set(matched_question.lower().split())
    for side_a, side_b in OPPOSITE_ACTION_PAIRS:
        if (user_words & side_a and matched_words & side_b) or (
            user_words & side_b and matched_words & side_a
        ):
            return True
    return False


def log_chat_interaction(question, classification, response):
    # Data-ethics rule: never store sensitive data patterns, even if the
    # user typed them in by mistake. Redact before the row is written.
    safe_question, _ = redact_sensitive(question)
    safe_response, _ = redact_sensitive(response)

    import os
    conn = get_connection()
    cur = conn.cursor()
    # SQLite only: on Azure SQL the chat_log table already exists
    # (created from azure_sql_schema.sql) and this syntax is not valid there.
    if os.environ.get("DB_BACKEND", "sqlite") == "sqlite":
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                question TEXT,
                classification TEXT,
                response TEXT
            )
            """
        )
    cur.execute(
        "INSERT INTO chat_log (timestamp, question, classification, response) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), safe_question, classification, safe_response),
    )
    conn.commit()
    conn.close()


@app.route("/ingest", methods=["POST"])
def ingest():
    """Write API: how new interaction data actually gets into Listener.

    This is what a channel adapter (chat, email, call transcript parser —
    see email_adapter.py for a worked example) calls once it has converted
    that channel's raw data into this common shape. Nothing about the rest
    of the system (matching, dashboard, insights) needs to know or care
    which channel a record came from -- that's the whole point of the
    common schema.

    Required fields: session_id, user_question, chatbot_response, channel
    Optional fields: timestamp (defaults to now), follow_up_question,
                      resolved, category, customer_id
    """
    data = request.get_json(silent=True) or {}

    required = ["session_id", "user_question", "chatbot_response", "channel"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required field(s): {', '.join(missing)}"}), 400

    # Same data-ethics rule as chat input: never store sensitive data,
    # even if it arrives through this API rather than the chat box.
    safe_question, _ = redact_sensitive(data["user_question"])
    safe_response, _ = redact_sensitive(data["chatbot_response"])

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO interactions
            (session_id, timestamp, user_question, chatbot_response,
             follow_up_question, resolved, category, channel, customer_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["session_id"],
            data.get("timestamp") or datetime.now().isoformat(),
            safe_question,
            safe_response,
            data.get("follow_up_question"),
            data.get("resolved"),
            data.get("category"),
            data["channel"],
            data.get("customer_id"),
        ),
    )
    conn.commit()
    conn.close()

    # A new record invalidates the cached question list used for matching.
    global _known_question_cache
    _known_question_cache = None

    return jsonify({"status": "ok"}), 201


@app.route("/chat", methods=["POST"])
def chat():
    user_msg = request.json.get("message", "").strip()

    if not user_msg:
        return jsonify({"response": "Please type a question."})

    if contains_inappropriate_content(user_msg):
        log_chat_interaction(user_msg, "flagged_inappropriate", MODERATION_REPLY)
        return jsonify({"response": MODERATION_REPLY})

    small_talk_type = classify_small_talk(user_msg)
    if small_talk_type == "greeting":
        response = random.choice(GREETING_REPLIES)
        log_chat_interaction(user_msg, "greeting", response)
        return jsonify({"response": response})
    if small_talk_type == "thanks":
        response = random.choice(THANKS_REPLIES)
        log_chat_interaction(user_msg, "thanks", response)
        return jsonify({"response": response})
    if small_talk_type == "goodbye":
        response = random.choice(GOODBYE_REPLIES)
        log_chat_interaction(user_msg, "goodbye", response)
        return jsonify({"response": response})
    if small_talk_type == "acknowledgement":
        response = random.choice(ACK_REPLIES)
        log_chat_interaction(user_msg, "acknowledgement", response)
        return jsonify({"response": response})

    if is_too_short_or_vague(user_msg):
        response = (
            "I want to make sure I understand — could you tell me a "
            "bit more about what you're asking?"
        )
        log_chat_interaction(user_msg, "unclear", response)
        return jsonify({"response": response})

    known_pairs = load_known_questions()
    q_emb = get_embedding(user_msg)

    best_score = 0.0
    best_answer = None
    best_question = None
    for question, answer, emb in known_pairs:
        score = cosine_similarity(q_emb, emb)
        if score > best_score:
            best_score = score
            best_answer = answer
            best_question = question

    mismatch = best_question is not None and is_opposite_action(user_msg, best_question)

    if best_score < SIMILARITY_THRESHOLD or best_answer is None or mismatch:
        response = random.choice(FALLBACK_REPLIES)
        log_chat_interaction(user_msg, "out_of_scope", response)
        return jsonify({"response": response})

    log_chat_interaction(user_msg, "resolved", best_answer)
    return jsonify({"response": best_answer})


if __name__ == "__main__":
    app.run(debug=True)