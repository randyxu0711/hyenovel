-- 每則 companion 發言是哪隻角色說的(hyena/buffalo/deer…);只有 den 討論的 assistant 那筆有值,其餘為 NULL。
ALTER TABLE utterance ADD COLUMN character TEXT;
