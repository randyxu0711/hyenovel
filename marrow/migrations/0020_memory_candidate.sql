CREATE TABLE memory_candidate (
  id INTEGER PRIMARY KEY,
  discussion_id INTEGER NOT NULL REFERENCES discussion(id),
  seq INTEGER NOT NULL, quote TEXT NOT NULL, text TEXT NOT NULL,
  scope TEXT NOT NULL CHECK (scope IN ('author', 'work')),
  created_at REAL NOT NULL,
  resolution TEXT CHECK (resolution IN ('saved', 'skipped')),
  resolved_at REAL, memory_id INTEGER REFERENCES memory(id));
CREATE INDEX memory_candidate_pending ON memory_candidate(created_at) WHERE resolution IS NULL;
