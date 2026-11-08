PRAGMA defer_foreign_keys = ON;
CREATE TEMP TABLE discussion_old AS SELECT * FROM discussion;
DROP TABLE discussion;
CREATE TABLE discussion (
  id INTEGER PRIMARY KEY, story_id INTEGER REFERENCES story(id),
  external_id TEXT NOT NULL UNIQUE, home TEXT NOT NULL, client TEXT,
  started_at REAL NOT NULL, ended_at REAL);
INSERT INTO discussion (id, story_id, external_id, home, client, started_at, ended_at)
  SELECT id, story_id, external_id, home, client, started_at, ended_at FROM discussion_old;
DROP TABLE discussion_old;
CREATE TABLE attachment (
  discussion_id INTEGER NOT NULL REFERENCES discussion(id),
  n INTEGER NOT NULL,
  seq INTEGER NOT NULL,
  name TEXT NOT NULL,
  text TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  added_at REAL NOT NULL,
  source_version_id INTEGER REFERENCES source_version(id),
  PRIMARY KEY (discussion_id, n));
