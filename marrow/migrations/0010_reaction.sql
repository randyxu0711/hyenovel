-- 作者對 assistant 回覆的回饋記號;配方靠 (discussion_id, seq) 對回 utterance.recipe。
CREATE TABLE reaction (
  discussion_id INTEGER NOT NULL, seq INTEGER NOT NULL,
  mark TEXT NOT NULL, comment TEXT, updated_at REAL NOT NULL,
  PRIMARY KEY (discussion_id, seq),
  FOREIGN KEY (discussion_id, seq) REFERENCES utterance(discussion_id, seq));
