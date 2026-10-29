-- 切片 4a:結論懸空(stale)改看「當時對照的 analysis artifact id」,取代 analysis.json 檔案 sha1。
-- 舊列為 NULL(匯入器在 fp 對得上時回填;對不上的維持 NULL = 視為懸空)。
ALTER TABLE conclusion ADD COLUMN analysis_artifact_id INTEGER REFERENCES artifact(id);
