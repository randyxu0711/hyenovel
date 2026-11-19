CREATE TABLE digest (
  id INTEGER PRIMARY KEY,
  root_id INTEGER REFERENCES digest(id),
  discussion_id INTEGER NOT NULL REFERENCES discussion(id),
  text TEXT NOT NULL, through_seq INTEGER NOT NULL, edited INTEGER NOT NULL DEFAULT 0,
  usage TEXT, recipe TEXT, created_at REAL NOT NULL, invalidated_at REAL);
CREATE INDEX digest_live ON digest(discussion_id) WHERE invalidated_at IS NULL;
CREATE TABLE digest_thread (
  id INTEGER PRIMARY KEY,
  root_id INTEGER NOT NULL REFERENCES digest(id),
  text TEXT NOT NULL, quote TEXT NOT NULL, source_quote TEXT, ended_at REAL, replaced_at REAL);
CREATE TABLE thread_talked (
  thread_id INTEGER NOT NULL REFERENCES digest_thread(id),
  discussion_id INTEGER NOT NULL REFERENCES discussion(id),
  PRIMARY KEY (thread_id, discussion_id));
CREATE TABLE digest_failure (
  discussion_id INTEGER PRIMARY KEY REFERENCES discussion(id),
  through_seq INTEGER NOT NULL, at REAL NOT NULL);
