# Listener - Python Analysis & Insights Service

Part of the OLT **Listener** project (CSMAX596 internship). This is the
Python-based analysis and insights engine, a Flask service
(`src/listener-python` in this repo) designed to sit alongside the
.NET/Aspire/Azure infrastructure and be called by it as a containerized
service, rather than being rewritten in .NET.

## What this does

Listener turns raw chatbot conversation logs into traceable insights:
which questions come up most, where users get stuck, which responses
fail most often, which questions are really the same question asked
differently (semantic clustering), and which customers see repeat,
unresolved issues.

Right now it runs against a **synthetic, non-PII dataset** (2,030 chat
records mapped to OLT's real product areas: MVC, Insights, Plant, plus 2
sample email records from the email adapter proof) rather than live
customer data. In the deployed version the data lives in **Azure SQL**;
for quick local development it can also run on a local SQLite file (see
"Database backend").

## Which way do I run it?

| I want to... | Database | Embeddings | Section |
|---|---|---|---|
| Try it on my laptop quickly | local SQLite | local Ollama | "Running locally" |
| Run my laptop against the real Azure SQL database | Azure SQL | local Ollama | "Running locally against Azure SQL" |
| Run the container locally | SQLite or Azure SQL | Ollama or Azure OpenAI | "Running in Docker" |
| See the live cloud version | Azure SQL | none yet (live chat not working in cloud) | "Cloud deployment" |

## Project structure

| File | Purpose |
|---|---|
| `app.py` | Main Flask app - dashboard (`/`), live JSON stats (`/stats`), chat UI (`/chat-page`), chat API (`/chat`), and the write API for new data (`/ingest`) |
| `db_connection.py` | Shared database connection helper. Connects to local SQLite or Azure SQL depending on the `DB_BACKEND` environment variable |
| `load_dataset.py` | Loads the current synthetic dataset (`OLT_Listener_Synthetic_Dataset_v3.xlsx`) into `olt_listener.db` |
| `add_customer_channel_fields.py` | Adds `Channel` and anonymized `Customer_ID` columns to the dataset (v2 -> v3) |
| `build_pipeline.py` | Original/legacy pipeline (86-record dataset) - kept for reference, superseded by `load_dataset.py` |
| `semantic_analysis.py` | Batch script: generates embeddings for all known questions and groups similar ones into clusters, saved to `semantic_clusters.json` |
| `test_matching.py` | Interactive debug tool for testing match scores and tuning `SIMILARITY_THRESHOLD` |
| `email_adapter.py` | Proof-of-concept channel adapter: shows how email-style records are converted into the common schema and sent to `/ingest` |
| `Templates/agent_instructions.md` | Written scope/behaviour spec for the chatbot (categories it can answer, escalation rules, logging requirements) |
| `Templates/index.html` | Dashboard page template |
| `Templates/chat_interface.html` | Chat page template |
| `DATA_ETHICS.md` | Policy defining what is/isn't stored, and how sensitive data typed into chat is redacted |
| `Dockerfile` / `.dockerignore` | Container build definition for deployment (includes the SQL Server ODBC driver) |
| `requirements.txt` | Python dependencies |
| `azure_sql_schema.sql` | Azure SQL (T-SQL) schema for the `interactions` and `chat_log` tables. Run once to create the tables |
| `export_for_azure_sql.py` | Exports the current SQLite data to CSV files |
| `make_insert_sql.py` | Reads the exported CSV files and generates `load_data.sql` (INSERT statements) for loading into Azure SQL. It only inserts into a table that is empty, so running it twice does not duplicate data |
| `seed_contact_form.py` | Seeds `dbo.ContactFormSubmissions` with synthetic rows (Faker). Truncates the table first, so it is repeatable |
| `olt_listener.db` | SQLite database (local only, not checked in for production use) |

`load_data.sql` and the exported CSV files are generated files and are not
committed.

## Database backend (SQLite vs Azure SQL)

Set via the `DB_BACKEND` environment variable (same pattern as
`EMBEDDING_BACKEND`):

- `sqlite` (default) - uses the local `olt_listener.db` file.
- `azure_sql` - uses Azure SQL. Requires these variables:

| Variable | Example |
|---|---|
| `AZURE_SQL_SERVER` | `listener-sql-server-deepika.database.windows.net` |
| `AZURE_SQL_DATABASE` | `listener-test-db` |
| `AZURE_SQL_USER` | `listeneradmin` |
| `AZURE_SQL_PASSWORD` | the server admin password (**never commit this**) |

The Python side needs the `pyodbc` package and the **ODBC Driver 18 for SQL
Server** installed on the machine (already included in the Docker image).

A few SQL statements differ between SQLite and Azure SQL (for example
`TOP 5` instead of `LIMIT 5`). `app.py` handles this with `DB_BACKEND`
checks, and the `chat_log` table is only auto-created on SQLite (on Azure SQL
it is created from `azure_sql_schema.sql`).

## How the chat matching works (current state)

The `/chat` endpoint is currently **retrieval-based**, not generative:

1. Free-text is first checked for inappropriate content (declines politely
   and logs it as `flagged_inappropriate`) and for sensitive data patterns
   (card numbers, SSN-style numbers - automatically redacted before
   anything is stored; see `DATA_ETHICS.md`).
2. Small-talk (greetings/thanks/goodbye) is caught with simple keyword matching.
3. Very short/vague input (2 words or fewer) triggers a clarification prompt.
4. Otherwise, the message is embedded and compared via cosine similarity
   against embeddings of every known question in the dataset. The
   embedding backend is configurable - see `EMBEDDING_BACKEND` below.
5. If the best match scores at least `SIMILARITY_THRESHOLD` (0.70) and isn't
   flagged as an opposite-intent mismatch (e.g. "cancel" vs "take" a
   subscription), its stored answer is returned. Otherwise, a
   fallback/out-of-scope reply is given.
6. Every interaction is logged to the `chat_log` table for analysis.

An LLM-generated (RAG-style) response layer was investigated but paused by
mentor direction in favour of expanding the dataset first - see `llm_backend.py`
(currently a placeholder for that future work).

## Embedding backend (local dev vs. production)

Set via the `EMBEDDING_BACKEND` environment variable:

- `ollama` (default) - uses a local Ollama model (`nomic-embed-text`). Free,
  no external dependency, works offline. Requires Ollama running locally.
- `azure_openai` - uses Azure OpenAI's embeddings API. Requires
  `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and
  `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` to be set. Intended for production,
  to match the org's existing Azure environment rather than hosting a
  model server. Only an **embedding model** deployment is needed (not a chat
  model).

## Running locally

```bash
pip install -r requirements.txt
ollama pull nomic-embed-text

python load_dataset.py          # build the database from the dataset
python semantic_analysis.py     # optional: generate semantic clusters
python app.py                   # start the dashboard + chat at http://127.0.0.1:5000
```

## Running locally against Azure SQL

Same as above, but point the app at Azure SQL instead of the SQLite file
(PowerShell shown; use `export` on Linux/macOS):

```powershell
$env:DB_BACKEND='azure_sql'
$env:AZURE_SQL_SERVER='<server>.database.windows.net'
$env:AZURE_SQL_DATABASE='<database>'
$env:AZURE_SQL_USER='<user>'
$env:AZURE_SQL_PASSWORD='<password>'
python app.py
```

On start-up the terminal prints `DB_BACKEND is set to: azure_sql` and a
`DEBUG server=... database=...` line, which confirms which database is used.

## Setting up the Azure SQL database

Done once for the sandbox database. To repeat it on a new database:

1. **Create the tables:** run `azure_sql_schema.sql` against the database
   (for example with the VS Code SQL Server extension, Azure Data Studio or
   the Azure Portal query editor).
2. **Export the data:** `python export_for_azure_sql.py` writes
   `interactions_export.csv` and `chat_log_export.csv`.
3. **Generate the load script:** `python make_insert_sql.py` writes
   `load_data.sql`.
4. **Load it:** run `load_data.sql` against the database. It ends with a row
   count per table (at the time of the first load: 2,032 `interactions` and
   107 `chat_log`).
5. **Optional - contact form data:** `dbo.ContactFormSubmissions` follows
   OLT's entity handoff (Id, ParentRetailerId, Category, SubmittedDate,
   UserId, Message). To fill it with synthetic data run
   `pip install faker`, set the `AZURE_SQL_*` variables, then
   `python seed_contact_form.py`. It loads 508 rows (the 8 sample rows from
   the handoff plus 500 synthetic rows using the real category values).
   Running it again resets the table to the same starting state.

## Azure SQL connection troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `Client with IP address ... is not allowed to access the server` | Your public IP is not in the server firewall. Add a rule for your current IP (Azure Portal -> the SQL server -> Networking, or accept the prompt in VS Code) and wait up to 5 minutes. Your IP changes when you switch networks, so you may need a new rule each time. |
| Login timeout, error 258 | The free serverless database pauses when idle and can take a minute to wake up. Retry once or twice. `db_connection.py` uses a longer connection timeout for this reason. |
| `Login failed` (18456) together with `Cannot open database ... requested by the login` (4060) | Check the **exact database name**. During development a leading space in the database name caused this: it worked in tools where the name was picked from a list, but failed wherever the name was typed. Connect to `master` and run `SELECT name FROM sys.databases`, print the names with `ascii()` or `repr()` to see hidden characters, and fix with `ALTER DATABASE [old name] MODIFY NAME = [new name]` (run from `master`). |
| Works on the laptop but not from the cloud app | The Azure SQL server must allow Azure services: in the server's Networking page enable "Allow Azure services and resources to access this server". |

## Adding a new channel (the ingest API)

Every channel (chat, email, calls) is converted by a small adapter into one
common shape and sent to `POST /ingest`. The rest of the system does not
care which channel a record came from - it is stored with a `channel` value.

- **Required fields:** `session_id`, `user_question`, `chatbot_response`, `channel`
- **Optional fields:** `timestamp` (defaults to now), `follow_up_question`,
  `resolved`, `category`, `customer_id`
- **Responses:** `201` with `{"status": "ok"}`, or `400` listing any missing
  required fields.
- Sensitive data patterns are redacted before anything is stored, the same
  as for chat input.
- `email_adapter.py` is a worked example.

```bash
curl -X POST http://127.0.0.1:5000/ingest \
  -H "Content-Type: application/json" \
  -d '{"session_id":"EMAIL-0003","user_question":"How do I reset my password?","chatbot_response":"You can reset it from Settings.","channel":"Email"}'
```

The endpoint currently has **no authentication** (see "Known limitations").

## Running in Docker

```bash
docker build -t listener-python .

# Local dev (talking to Ollama on your host machine):
docker run -p 5000:5000 \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  --add-host=host.docker.internal:host-gateway \
  listener-python

# Against Azure SQL (Ollama still on the host for embeddings):
docker run -p 5000:5000 \
  -e DB_BACKEND=azure_sql \
  -e AZURE_SQL_SERVER=<server>.database.windows.net \
  -e AZURE_SQL_DATABASE=<database> \
  -e AZURE_SQL_USER=<user> \
  -e AZURE_SQL_PASSWORD=<password> \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  --add-host=host.docker.internal:host-gateway \
  listener-python

# Production-style (Azure SQL + Azure OpenAI embeddings, no Ollama needed):
docker run -p 5000:5000 \
  -e DB_BACKEND=azure_sql \
  -e AZURE_SQL_SERVER=<server>.database.windows.net \
  -e AZURE_SQL_DATABASE=<database> \
  -e AZURE_SQL_USER=<user> \
  -e AZURE_SQL_PASSWORD=<password> \
  -e EMBEDDING_BACKEND=azure_openai \
  -e AZURE_OPENAI_ENDPOINT=<endpoint> \
  -e AZURE_OPENAI_API_KEY=<key> \
  -e AZURE_OPENAI_EMBEDDING_DEPLOYMENT=<deployment-name> \
  listener-python
```

The image installs the Microsoft ODBC Driver 18 for SQL Server and runs the
app with gunicorn (with a longer request timeout, so the first request after
the free database has been idle does not time out).

## Cloud deployment (live proof-of-concept)

The container has been pushed to Docker Hub and deployed to Azure Container
Apps, confirming the Python engine can run as an independent cloud service:

**Live URL:** `https://listener-python-app.salmongrass-b3126dd0.westus2.azurecontainerapps.io`

- The deployment runs from the Docker Hub image (currently tag `v11`).
- It reads from **Azure SQL**. The Container App is configured with the
  environment variables `DB_BACKEND=azure_sql`, `AZURE_SQL_SERVER`,
  `AZURE_SQL_DATABASE`, `AZURE_SQL_USER` and `AZURE_SQL_PASSWORD`.
  `/stats` shows the live record count (`total_interactions`), which is a
  quick way to confirm the data comes from Azure SQL.
- Dashboard and insights work fully on this deployment.
- **The live chat demo does not currently work in this cloud deployment** -
  Ollama isn't available in the container environment, and Azure OpenAI
  credentials are not yet available within the sandbox subscription used for
  this deployment (access has been requested; only an embedding model
  deployment is needed). The `EMBEDDING_BACKEND=azure_openai` switch is
  implemented and ready - it just needs real credentials to be tested end
  to end in the cloud. The chat works correctly locally with Ollama, both on
  SQLite and on Azure SQL.
- The endpoint is currently **public and unauthenticated** - acceptable for
  this demo/proof stage, but authentication would be needed before any
  production use.
- The Docker Hub image was pushed from a personal account for this
  proof-of-concept. For real production use, the image should be rebuilt
  from this repo's `Dockerfile` and pushed to an OLT-owned registry (Docker
  Hub org account or Azure Container Registry) instead.
- Images are built and pushed manually (there is no CI/CD pipeline yet).

## Known limitations

- Synthetic data only - not yet validated against real chatbot logs. Match
  accuracy (thresholds, categories) will likely need re-tuning once real
  conversation data is available - this is expected, not a defect.
  `dbo.ContactFormSubmissions` is also filled with synthetic (Faker) data.
- Chat matching is retrieval-only; no generative/RAG layer yet.
- Live chat demo doesn't work in the current cloud deployment (see "Cloud
  deployment" above) - works correctly locally with Ollama.
- Cloud endpoint is public/unauthenticated (demo stage only), and so is
  `/ingest`.
- The database password is stored as a plain environment variable in the
  Container App. For production use a Container Apps secret or Azure Key
  Vault, and prefer Entra/managed identity over a SQL admin login.
- The Azure SQL database is on the free serverless tier: it pauses when idle,
  so the first request after a quiet period can be slow, and firewall rules
  are per IP address.
- Only the chat channel has been built and tested end to end. The email
  adapter is a proof of concept on sample records, and call adapters are
  designed but not implemented (see "Planned next steps").
- `dbo.ContactFormSubmissions` is not yet connected to the dashboard: it
  holds contact-form messages and categories, but no chatbot response or
  resolved status, so it needs an adapter before it can feed `interactions`.

## Planned next steps

- Connect `dbo.ContactFormSubmissions` as a second real channel: an adapter
  that maps it into the common schema (with its own `channel` value) without
  changing the core analysis pipeline.
- Once real OLT data is available: re-tune matching thresholds and
  categories against it, and build the production ingestion pipeline
  (scheduled or real-time) that feeds new conversations in automatically.
- Get an Azure OpenAI embedding model deployment, so live chat can run in the
  cloud.
- Move the moderation term list (`INAPPROPRIATE_TERMS` in `app.py`) out of
  code and into a config/database table the support team can maintain
  directly.
- Add authentication (including on `/ingest`) and move secrets to Key Vault
  before any production/public exposure.
- Set up an automated build and deploy pipeline.