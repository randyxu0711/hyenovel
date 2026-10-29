-- 切片 3 Task 9e:attempt 記該次工人 system prompt 全文的 sha256 前 12 碼。
-- prompt 是 repo 檔案,改過就重建不出當時那版;舊列為 NULL。
ALTER TABLE attempt ADD COLUMN prompt_sha TEXT;
