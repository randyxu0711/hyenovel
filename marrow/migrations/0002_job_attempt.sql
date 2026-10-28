-- 切片 2:job 綁到產出時的那一版原文;attempt 記結局與產出的 artifact;佇列掃描索引。
ALTER TABLE job ADD COLUMN source_version_id INTEGER REFERENCES source_version(id);
ALTER TABLE job ADD COLUMN detail TEXT;
ALTER TABLE attempt ADD COLUMN outcome TEXT;
ALTER TABLE attempt ADD COLUMN artifact_id INTEGER REFERENCES artifact(id);
CREATE INDEX job_state ON job(state, id);
