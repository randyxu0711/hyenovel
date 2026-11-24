CREATE TABLE llm_call (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('analyst', 'reviewer', 'chat', 'redo', 'compact', 'digest', 'candidates', 'candidate_revise')),
  started_at REAL NOT NULL, ended_at REAL, duration_ms INTEGER,
  outcome TEXT CHECK (outcome IN ('ok', 'transient', 'usage-limit', 'auth', 'crash', 'timeout', 'cancelled', 'gate_rejected', 'discarded')),
  story_id INTEGER, job_id INTEGER, step TEXT, n INTEGER,
  discussion_id INTEGER, seq INTEGER, variant INTEGER, digest_id INTEGER, character_id TEXT,
  tokens TEXT, tokens_partial INTEGER NOT NULL DEFAULT 0, cost_usd REAL, model TEXT,
  prompt_fp TEXT NOT NULL, sizes TEXT, tag TEXT, rate_limit TEXT);
CREATE INDEX llm_call_started ON llm_call(started_at);
CREATE INDEX llm_call_kind ON llm_call(kind, started_at);
