CREATE TABLE character (
  id TEXT PRIMARY KEY,
  origin TEXT NOT NULL CHECK (origin IN ('builtin', 'imported', 'created')),
  created_at REAL NOT NULL,
  archived_at REAL);
CREATE TABLE character_version (
  character_id TEXT NOT NULL REFERENCES character(id),
  n INTEGER NOT NULL,
  card TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  created_at REAL NOT NULL,
  PRIMARY KEY (character_id, n));
CREATE TABLE setting (key TEXT PRIMARY KEY, value TEXT NOT NULL);
