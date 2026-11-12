ALTER TABLE utterance ADD COLUMN variant INTEGER NOT NULL DEFAULT 1;
ALTER TABLE utterance ADD COLUMN edited_at REAL;
CREATE TABLE utterance_variant (
  discussion_id INTEGER NOT NULL, seq INTEGER NOT NULL, n INTEGER NOT NULL,
  text TEXT NOT NULL, ts REAL NOT NULL, usage TEXT, recipe TEXT, analysis_fp TEXT, edited_at REAL,
  PRIMARY KEY (discussion_id, seq, n),
  FOREIGN KEY (discussion_id, seq) REFERENCES utterance(discussion_id, seq));
CREATE TABLE voice_mark (
  discussion_id INTEGER NOT NULL, seq INTEGER NOT NULL, variant INTEGER NOT NULL,
  marked_at REAL NOT NULL,
  PRIMARY KEY (discussion_id, seq, variant),
  FOREIGN KEY (discussion_id, seq) REFERENCES utterance(discussion_id, seq));
CREATE TEMP TABLE reaction_old AS SELECT * FROM reaction;
DROP TABLE reaction;
CREATE TABLE reaction (
  discussion_id INTEGER NOT NULL, seq INTEGER NOT NULL, variant INTEGER NOT NULL,
  mark TEXT NOT NULL, comment TEXT, updated_at REAL NOT NULL,
  PRIMARY KEY (discussion_id, seq, variant),
  FOREIGN KEY (discussion_id, seq) REFERENCES utterance(discussion_id, seq));
INSERT INTO reaction (discussion_id, seq, variant, mark, comment, updated_at)
  SELECT discussion_id, seq, 1, mark, comment, updated_at FROM reaction_old;
DROP TABLE reaction_old;
