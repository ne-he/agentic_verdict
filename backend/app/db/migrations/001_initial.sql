-- Migration 001 — Initial schema (T3.4)
-- Jalankan sekali untuk setup DB manual (SQLAlchemy create_all() juga bisa dipakai).
-- Tidak ada syntax SQLite-only supaya portable ke Postgres (Neon).

CREATE TABLE IF NOT EXISTS run_history (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           VARCHAR(64)  NOT NULL UNIQUE,
    dataset_id       VARCHAR(128) NOT NULL,
    dataset_snapshot VARCHAR(80)  NOT NULL DEFAULT '',
    question         TEXT         NOT NULL,
    answer_markdown  TEXT         NOT NULL,
    code             TEXT         NOT NULL DEFAULT '',
    tokens           INTEGER      NOT NULL DEFAULT 0,
    cost_usd         FLOAT        NOT NULL DEFAULT 0.0,
    duration_ms      INTEGER      NOT NULL DEFAULT 0,
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scorecards (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id               VARCHAR(64) NOT NULL UNIQUE REFERENCES run_history(run_id),
    question_id          VARCHAR(32) NOT NULL DEFAULT '',
    correctness          FLOAT       NOT NULL,
    cost_usd             FLOAT       NOT NULL DEFAULT 0.0,
    tool_calls           INTEGER     NOT NULL DEFAULT 0,
    time_to_insight      FLOAT       NOT NULL DEFAULT 0.0,
    hallucination_flag   BOOLEAN     NOT NULL DEFAULT FALSE,
    verification_accuracy FLOAT      NOT NULL DEFAULT 0.0,
    created_at           TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gold_questions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id       VARCHAR(32)  NOT NULL UNIQUE,
    dataset_id        VARCHAR(128) NOT NULL,
    category          VARCHAR(32)  NOT NULL,
    question          TEXT         NOT NULL,
    gold_answer       TEXT         NOT NULL,
    expected_value    FLOAT        NOT NULL,
    allowed_tolerance FLOAT        NOT NULL DEFAULT 0.01,
    is_trap           BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS artifacts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        VARCHAR(64) NOT NULL REFERENCES run_history(run_id),
    artifact_type VARCHAR(32) NOT NULL,
    file_path     TEXT        NOT NULL,
    created_at    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_run_history_run_id   ON run_history(run_id);
CREATE INDEX IF NOT EXISTS idx_scorecards_run_id    ON scorecards(run_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_run_id     ON artifacts(run_id);
