# Listener — Data-Ethics Policy

This document defines what Listener will and will not record, and why. It
exists so the answer to "would this be recorded?" is decided in advance,
not improvised per conversation.

## Principle

Listener's job is to find **patterns**, not to build a record of any
individual. Nothing should be stored that isn't needed to identify a
pattern across many conversations.

## Never stored, under any circumstances

The following are actively detected and stripped before anything is
written to the database (see `redact_sensitive()` in `app.py`):

- Payment card numbers
- National ID / SSN-style numbers

If a customer accidentally types one of these into a chat, the message is
still logged (for the surrounding context) but the sensitive portion is
replaced with `[redacted]` before it ever reaches storage.

## Never stored, by design (no field exists for this)

- Customer name, email address, phone number, or physical address
- Free-text notes written by a human support agent about a customer

Because these have no column in the schema, this is enforced structurally,
not just by a filter — there's nothing to remember to redact.

## Stored, but anonymized

- **Customer_ID** — a synthetic, randomly-assigned identifier (e.g.
  `CUST-0247`), used only to detect repeat/unresolved patterns for the
  *same* customer over time. It cannot be traced back to a real person
  without access to OLT's own separate customer systems, which Listener
  never connects to.

## What happens to flagged/inappropriate messages

Messages containing abusive or harmful language are still logged (see
`flagged_inappropriate` in the chat activity table) — the *fact* that it
happened is a useful signal for the support team, but the response given
is a fixed decline message, not a generated one, so there's no risk of
the system engaging with harmful input.

## Open question for OLT (flag for mentor/report)

This policy currently applies to the **synthetic dataset and the local
chat testing tool**. Before Listener is ever pointed at real OLT customer
logs, this same policy needs to be re-confirmed against whatever privacy/
data-retention rules OLT already has for its own systems — Listener should
follow the stricter of the two, not define its own standard in isolation.
