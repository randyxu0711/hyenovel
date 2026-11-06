UPDATE utterance SET character = CASE mode WHEN 'slow' THEN 'hyena' WHEN 'direct' THEN 'buffalo'
  WHEN 'imaginative' THEN 'deer' END WHERE character IS NULL AND mode IS NOT NULL;
ALTER TABLE utterance DROP COLUMN mode;
