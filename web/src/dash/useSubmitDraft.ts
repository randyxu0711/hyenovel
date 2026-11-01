import { useCallback, useEffect, useState } from "react";
import { api, DashError, type Estimate, type SubmitResult } from "./api";

const RESTART = ["none", "stopped", "notes-stopped"];

/** 貼上超過這個字數就當稿子(不是訊息)。 */
export const DRAFT_MIN_CHARS = 2000;

export type Draft = { text: string; title?: string; chars: number; estimate: { v: Estimate | null } | null };

/** 交稿:檔案抽取/貼上 → 字數與預估 → 確認 → 交稿並開跑(或切到已存在的同稿)。 */
export function useSubmitDraft() {
  const [raw, setRaw] = useState<{ text: string; title?: string } | null>(null);
  const [est, setEst] = useState<{ chars: number; v: Estimate | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chars = raw ? raw.text.trim().length : 0;

  useEffect(() => {
    if (!chars) return;
    let live = true;
    api.estimate(chars).then(v => { if (live) setEst({ chars, v }); }, () => { if (live) setEst({ chars, v: null }); });
    return () => { live = false; };
  }, [chars]);

  const fail = (e: unknown) => setError(e instanceof DashError ? e.code : "unknown");
  const fromText = useCallback((text: string) => { setError(null); setRaw({ text }); }, []);
  const fromFile = useCallback(async (file: File) => {
    setError(null);
    try {
      const r = await api.extract(file);
      setRaw({ text: r.text, title: r.filename.replace(/\.(md|txt)$/i, "") });
    } catch (e) { fail(e); }
  }, []);
  const cancel = useCallback(() => { setRaw(null); setEst(null); setError(null); setBusy(false); }, []);

  /** 成功回交稿結果(reused = 已有同稿、沒開新 job);失敗設 error 並回 null。 */
  const confirm = useCallback(async (): Promise<SubmitResult | null> => {
    if (!raw || !chars || busy) return null;
    setBusy(true); setError(null);
    try {
      const r = await api.submit(raw.text, raw.title);
      if (r.reused) {
        // 上次可能交稿成功但沒開成 job:沒分析過或停住的才補開(den 會續跑,不重跑)
        const w = await api.work(r.slug);
        if (RESTART.includes(w.state)) await api.startJob(r.slug);
      } else await api.startJob(r.slug);
      setRaw(null); setEst(null); setBusy(false);
      return r;
    } catch (e) { fail(e); setBusy(false); return null; }
  }, [raw, chars, busy]);

  const draft: Draft | null = raw && {
    ...raw, chars, estimate: est && est.chars === chars ? { v: est.v } : null,
  };
  return { draft, busy, error, fromFile, fromText, confirm, cancel };
}
