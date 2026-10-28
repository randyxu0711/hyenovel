-- 初版表結構(spec §3.5)。冪等鍵(sha256 / external_id / (discussion_id, seq))是 R1 的要求:
-- 過渡期匯入器要能對同一份舊檔重跑而不重複。job / attempt 本片不寫入,先建,免得切片 2 一開頭就是 migration。
CREATE TABLE story (
  id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, title TEXT, created_at REAL NOT NULL);
CREATE TABLE source_version (
  id INTEGER PRIMARY KEY, story_id INTEGER NOT NULL REFERENCES story(id),
  n INTEGER NOT NULL, text TEXT NOT NULL, sha256 TEXT NOT NULL, created_at REAL NOT NULL,
  UNIQUE (story_id, n), UNIQUE (story_id, sha256));
CREATE TABLE artifact (
  id INTEGER PRIMARY KEY, story_id INTEGER NOT NULL REFERENCES story(id),
  source_version_id INTEGER NOT NULL REFERENCES source_version(id),
  kind TEXT NOT NULL, schema_version INTEGER NOT NULL, body TEXT NOT NULL, sha256 TEXT NOT NULL,
  provenance TEXT NOT NULL, created_at REAL NOT NULL,
  UNIQUE (story_id, kind, sha256));
CREATE TABLE current_artifact (
  story_id INTEGER NOT NULL REFERENCES story(id), kind TEXT NOT NULL,
  artifact_id INTEGER NOT NULL REFERENCES artifact(id), PRIMARY KEY (story_id, kind));
CREATE TABLE job (
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, story_id INTEGER REFERENCES story(id),
  state TEXT NOT NULL, step TEXT, params TEXT NOT NULL, error_class TEXT,
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE attempt (
  id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES job(id), step TEXT NOT NULL,
  n INTEGER NOT NULL, runner TEXT NOT NULL, model TEXT, cli_version TEXT, input_ref TEXT,
  raw_output TEXT, parsed TEXT, gate_verdict TEXT, tokens TEXT, duration_ms INTEGER,
  created_at REAL NOT NULL, UNIQUE (job_id, step, n));
CREATE TABLE discussion (
  id INTEGER PRIMARY KEY, story_id INTEGER NOT NULL REFERENCES story(id),
  external_id TEXT NOT NULL, home TEXT NOT NULL, client TEXT,
  started_at REAL NOT NULL, ended_at REAL, UNIQUE (story_id, external_id));
CREATE TABLE utterance (
  discussion_id INTEGER NOT NULL REFERENCES discussion(id), seq INTEGER NOT NULL,
  role TEXT NOT NULL, text TEXT NOT NULL, ts REAL NOT NULL, origin TEXT NOT NULL,
  anchors TEXT NOT NULL, analysis_fp TEXT, PRIMARY KEY (discussion_id, seq));
CREATE TABLE conclusion (
  id INTEGER PRIMARY KEY, story_id INTEGER NOT NULL REFERENCES story(id),
  external_id TEXT NOT NULL, discussion_id INTEGER REFERENCES discussion(id),
  kind TEXT NOT NULL, text TEXT NOT NULL, refs TEXT NOT NULL, quotes TEXT NOT NULL,
  provenance TEXT NOT NULL, valid_from REAL NOT NULL, invalidated_at REAL,
  UNIQUE (story_id, external_id));
CREATE TABLE settlement (
  discussion_id INTEGER NOT NULL UNIQUE REFERENCES discussion(id),
  settled_at REAL NOT NULL, written INTEGER NOT NULL);
