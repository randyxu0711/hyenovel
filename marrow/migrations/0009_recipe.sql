-- 配方:prompt 每層指紋 + run config,回饋與產物才對得回版本;舊列為 NULL。
ALTER TABLE attempt ADD COLUMN recipe TEXT;
ALTER TABLE utterance ADD COLUMN recipe TEXT;
