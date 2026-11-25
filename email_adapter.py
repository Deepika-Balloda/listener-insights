"""
Email channel adapter — proof of concept.

This demonstrates the whole point of the channel-agnostic design: a new
channel (email, here) can be plugged in by writing ONE small adapter that
converts that channel's raw format into Listener's common schema, then
calls the existing /ingest API. Nothing in app.py, the matching logic, or
the dashboard needs to change for a new channel to start showing up.

In production, "raw email data" would come from something like Microsoft
Graph API (reading a shared support mailbox). Here, it's a small set of
realistic sample emails, since real OLT email data isn't available during
this internship -- see README.md "Known limitations".

Run (with app.py already running separately, e.g. `python app.py`):
    python email_adapter.py
"""

import re
import requests

INGEST_URL = "http://127.0.0.1:5000/ingest"

# Sample raw emails, in a realistic "as received" shape: a subject line
# and a body, nothing structured. This is what a real inbox export would
# look like before any processing.
SAMPLE_EMAILS = [
    {
        "email_id": "EMAIL-0001",
        "from": "customer-a@example.com",
        "received": "2026-09-20T09:14:00",
        "subject": "Can't reset my password",
        "body": (
            "Hi team,\n\n"
            "I've been trying to reset my password for the last hour and the "
            "reset link in the email never arrives. Can someone help?\n\n"
            "Thanks"
        ),
    },
    {
        "email_id": "EMAIL-0002",
        "from": "customer-b@example.com",
        "received": "2026-09-20T11:02:00",
        "subject": "Question about my last bill",
        "body": (
            "Hello,\n\n"
            "My latest bill looks higher than usual and I can't see a "
            "breakdown anywhere in the portal. Where can I check this?\n\n"
            "Regards"
        ),
    },
]


def parse_email_to_record(email, session_counter):
    """Converts one raw email into Listener's common schema.

    This is deliberately simple (rule-based, not ML) -- the point of this
    proof-of-concept is the SHAPE of the adapter pattern, not sophisticated
    email parsing. A production version might use an LLM or NLP library to
    extract the actual question more precisely, but the schema and pipeline
    below stay exactly the same either way.
    """
    # Strip a common greeting/sign-off so "user_question" is closer to the
    # actual ask, similar in spirit to how a support agent would read it.
    body = email["body"]
    body = re.sub(r"^(hi|hello|hey)[,!\s]*(team)?[,!\s]*", "", body.strip(), flags=re.IGNORECASE)
    body = re.sub(r"(thanks|regards|best)[,!\s]*$", "", body.strip(), flags=re.IGNORECASE)
    question_text = " ".join(body.split())  # collapse whitespace/newlines

    return {
        "session_id": email["email_id"],
        "timestamp": email["received"],
        "user_question": f"{email['subject']} — {question_text}",
        "chatbot_response": "[Awaiting human support reply — not yet answered by Listener]",
        "follow_up_question": None,
        "resolved": "Unclear",
        "category": None,  # would need the same categorisation logic used for chat, applied here too
        "channel": "Email",
        "customer_id": f"CUST-EMAIL-{session_counter:04d}",  # placeholder anonymized ID for this POC
    }


def main():
    sent = 0
    for i, email in enumerate(SAMPLE_EMAILS, start=1):
        record = parse_email_to_record(email, i)
        response = requests.post(INGEST_URL, json=record)
        if response.status_code == 201:
            print(f"Ingested {record['session_id']}: {record['user_question'][:60]}...")
            sent += 1
        else:
            print(f"Failed to ingest {record['session_id']}: {response.status_code} {response.text}")

    print(f"\nDone. {sent}/{len(SAMPLE_EMAILS)} sample emails ingested as channel='Email'.")
    print("Check the dashboard's 'Interactions by channel' table — it should now show Email alongside Chat.")


if __name__ == "__main__":
    main()
