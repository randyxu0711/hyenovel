-- 每輪 companion 用的行為模式(direct/slow/imaginative);只有 den 討論的 assistant 那筆有值,其餘為 NULL。
ALTER TABLE utterance ADD COLUMN mode TEXT;
