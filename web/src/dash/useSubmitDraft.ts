import { useCallback, useEffect, useState } from "react";
import { api, DashError, type Estimate, type SubmitResult } from "./api";

const RESTART = ["none", "stopped", "notes-stopped"];

/** 貼上超過這個字數就當稿子(不是訊息)。 */
export const DRAFT_MIN_CHARS = 2000;

export type Draft = { text: string; title?: string; chars: number; estimate: { v: Estimate | null } | null };

/** 交稿:檔案抽取/貼上 → 字數與預估 → 確認 → 交稿並開跑(或切到已存在的同稿)。帶 slug = 交成該篇的新版。 */
export function useSubmitDraft(slug?: string) {
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
      if (!r.text.trim()) setError("empty-story");   // 只有空白的檔:別讓交稿鍵按了沒反應
    } catch (e) { fail(e); }
  }, []);
  const cancel = useCallback(() => { setRaw(null); setEst(null); setError(null); setBusy(false); }, []);

  /** 成功回交稿結果(reused = 已有同稿、沒開新 job;same = 帶 slug 時與最新版一字不差);失敗設 error 並回 null。
   *  帶 slug 時 analyze=false 只存版不開 job;新版已存下但開 job 失敗 → 照樣回結果,錯誤碼在 jobError。 */
  const confirm = useCallback(async (opts: { analyze?: boolean } = {}): Promise<(SubmitResult & { same: boolean; jobError?: string }) | null> => {
    if (!raw || busy) return null;
    if (!chars) { setError("empty-story"); return null; }
    setBusy(true); setError(null);
    try {
      const r = slug ? await api.submit(raw.text, undefined, slug) : await api.submit(raw.text, raw.title);
      const same = !!slug && !r.new_version;
      if (slug ? same : r.reused) {
        // 上次可能交稿成功但沒開成 job:沒分析過或停住的才補開(den 會續跑,不重跑)
        const w = await api.work(r.slug);
        if (RESTART.includes(w.state)) {
          if (slug) await api.startJob(r.slug, { resumeOnly: true }).catch(e => { if (!(e instanceof DashError && e.status === 409)) throw e; });
          else await api.startJob(r.slug);
        }
      } else if (!slug) await api.startJob(r.slug);
      else if (opts.analyze !== false) {
        try { await api.startJob(r.slug); } catch (e) {
          // 新版已經存下:稿不留(重交會變成「一字不差」),交給呼叫端回最新版並顯示錯誤
          setRaw(null); setEst(null); setBusy(false);
          return { ...r, same, jobError: e instanceof DashError ? e.code : "unknown" };
        }
      }
      setRaw(null); setEst(null); setBusy(false);
      return { ...r, same };
    } catch (e) { fail(e); setBusy(false); return null; }
  }, [raw, chars, busy, slug]);

  const draft: Draft | null = raw && {
    ...raw, chars, estimate: est && est.chars === chars ? { v: est.v } : null,
  };
  return { draft, busy, error, fromFile, fromText, confirm, cancel };
}
