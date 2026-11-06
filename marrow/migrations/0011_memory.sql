CREATE TABLE memory (
  id INTEGER PRIMARY KEY,
  root_id INTEGER REFERENCES memory(id),
  scope TEXT NOT NULL CHECK (scope IN ('author', 'work', 'character')),
  story_id INTEGER REFERENCES story(id),
  character TEXT,
  text TEXT NOT NULL,
  quote TEXT,
  discussion_id INTEGER,
  seq INTEGER,
  valid_from REAL NOT NULL,
  learned_at REAL NOT NULL,
  invalidated_at REAL,
  CHECK ((scope = 'work') = (story_id IS NOT NULL)),
  CHECK ((scope = 'character') = (character IS NOT NULL)),
  CHECK ((quote IS NULL) = (discussion_id IS NULL) AND (quote IS NULL) = (seq IS NULL)),
  FOREIGN KEY (discussion_id, seq) REFERENCES utterance(discussion_id, seq));
CREATE INDEX memory_active ON memory(scope, story_id) WHERE invalidated_at IS NULL;
