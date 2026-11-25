-- ===========================================================================
-- Listener — Azure SQL schema (translated from local SQLite)
--
-- This is a MIGRATION PROOF, not a live migration: it demonstrates that the
-- current SQLite schema maps cleanly onto Azure SQL with no structural
-- changes needed, only SQLite's loose typing becoming Azure SQL's stricter
-- types. Run this against an actual Azure SQL database (via Azure Data
-- Studio, SSMS, or `sqlcmd`) once OLT provisions one.
--
-- SQLite -> Azure SQL type mapping used below:
--   SQLite TEXT (session/customer IDs, short codes)  -> NVARCHAR(100)
--   SQLite TEXT (long conversation text)             -> NVARCHAR(MAX)
--   SQLite TEXT (timestamp stored as ISO string)      -> DATETIME2
--   SQLite INTEGER AUTOINCREMENT                      -> INT IDENTITY(1,1)
-- ===========================================================================

CREATE TABLE interactions (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    session_id          NVARCHAR(100)   NOT NULL,
    [timestamp]         DATETIME2       NOT NULL,
    user_question       NVARCHAR(MAX)   NOT NULL,
    chatbot_response    NVARCHAR(MAX)   NOT NULL,
    follow_up_question  NVARCHAR(MAX)   NULL,
    resolved            NVARCHAR(20)    NULL,   -- 'Yes' / 'No' / 'Unclear'
    category             NVARCHAR(200)   NULL,
    channel             NVARCHAR(50)    NULL,   -- 'Chat' / 'Call' / 'Email'
    customer_id          NVARCHAR(50)    NULL    -- anonymized synthetic ID
);

-- Indexes matching how the dashboard actually queries this table
-- (see app.py: grouped by customer_id, filtered/grouped by channel and
-- category, and resolved/unresolved counts).
CREATE INDEX IX_interactions_customer_id ON interactions (customer_id);
CREATE INDEX IX_interactions_channel     ON interactions (channel);
CREATE INDEX IX_interactions_category    ON interactions (category);


CREATE TABLE chat_log (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    [timestamp]     DATETIME2       NOT NULL,
    question        NVARCHAR(MAX)   NOT NULL,
    classification  NVARCHAR(50)    NOT NULL,  -- e.g. 'resolved', 'flagged_inappropriate'
    response        NVARCHAR(MAX)   NOT NULL
);

CREATE INDEX IX_chat_log_classification ON chat_log (classification);

-- ===========================================================================
-- Notes on what would change in app.py when pointed at Azure SQL instead
-- of SQLite (not done yet — this script only proves the schema translates
-- cleanly; the application-side change is a separate, small step):
--
--   - Swap sqlite3.connect(DB_PATH) for a pyodbc/pymssql connection using
--     an Azure SQL connection string (would follow the same env-var-driven
--     pattern as EMBEDDING_BACKEND, e.g. DB_BACKEND=sqlite|azure_sql).
--   - SQL syntax used elsewhere in app.py (SELECT/GROUP BY/JOIN) is
--     standard ANSI SQL and needs no changes — only the connection layer
--     and this schema differ between SQLite and Azure SQL.
-- ===========================================================================
