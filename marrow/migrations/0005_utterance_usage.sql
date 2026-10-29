-- 每輪用量:只有 den 討論的 assistant 那筆有值(JSON:tokens + duration_ms + model),其餘為 NULL。
ALTER TABLE utterance ADD COLUMN usage TEXT;
