-- 使用者那一則「帶這段」帶的原文引文(JSON 陣列);其餘為 NULL。
ALTER TABLE utterance ADD COLUMN quotes TEXT;
