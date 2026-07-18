import { useCallback, useEffect, useRef, useState } from "react";
import { getRunningCritiques, streamCritique, cancelCritique, getIndex, reanalyzeCritique } from "../data/client";
import type { Gestation, GestationStatus } from "../types";

const STEP: Record<string, number> = { analyst: 1, criticizer: 2, render: 3 };

// index 的 status 值域不封閉(carried note:可能是 "cancelled" 等)——只有 "paused" 原樣保留,
// 其餘任何值一律當 "failed"(resumable=true 已保證它值得續跑,只是不知道確切原因)。
const resumedStatus = (status: string): GestationStatus => status === "paused" ? "paused" : "failed";

// 撞牆提示跨重整記住(F5 不消失):存 resets_at(可 null);到重置時刻或讀取時已過期就清掉。
const USAGE_KEY = "hy:usageLimit";
function loadUsageLimit(): number | null | undefined {
  try {
    const raw = localStorage.getItem(USAGE_KEY);
    if (raw === null) return undefined;
    const v = JSON.parse(raw) as number | null;
    if (typeof v === "number" && v * 1000 <= Date.now()) { localStorage.removeItem(USAGE_KEY); return undefined; }
    return v;
  } catch { return undefined; }
}
function saveUsageLimit(v: number | null | undefined) {
  try {
    if (v === undefined) localStorage.removeItem(USAGE_KEY);
    else localStorage.setItem(USAGE_KEY, JSON.stringify(v));
  } catch { /* localStorage 不可用就算了 */ }
}

// 獨佔後端孕育狀態:載入時併 /running、逐篇訂閱 SSE 更新 step、done → 誕生(onBorn+移除)。
// 連線斷了不影響後端 Run;重整後靠 /running + 重訂閱把胚胎接回來。
// 每條訂閱帶一個單調遞增 epoch;cancel 或對同 slug 重新 begin 會作廢舊 epoch,使舊串流的殘留
// 事件(如取消 error)不再改狀態 —— 避免 cancel→立即 re-begin 的競態誤刪新胎。
export function useGestations(onBorn: (slug: string) => void | Promise<void>) {
  const [gestations, setGestations] = useState<Map<string, Gestation>>(new Map());
  const [usageLimitResetAt, setUsageLimitResetAt] = useState<number | null | undefined>(loadUsageLimit);  // undefined=無提示;resets_at(可 null)。初值讀持久化 → F5 不消失
  const epochs = useRef<Map<string, number>>(new Map());  // slug -> 當前有效訂閱的 epoch
  const seq = useRef(0);                                    // 全域單調遞增,epoch 永不重用
  const onBornRef = useRef(onBorn);
  onBornRef.current = onBorn;

  const put = (slug: string, title: string, step: number, status: GestationStatus = "running",
               vizReady?: boolean, reason?: string, resetsAt?: number | null) =>
    setGestations(m => {
      const n = new Map(m);
      const cur = n.get(slug);
      n.set(slug, { title: title || cur?.title || slug, status, step: Math.max(step, cur?.step ?? 0),
                    vizReady: vizReady ?? cur?.vizReady,      // 一旦 true 就不再回頭(檔案不會消失)
                    reason, resetsAt });
      return n;
    });
  const drop = (slug: string) =>
    setGestations(m => { const n = new Map(m); n.delete(slug); return n; });

  // streamFn 預設 streamCritique(重接既有 Run / 新孕育);reanalyze() 傳 reanalyzeCritique 換掉它,
  // 讓「觸發 + 接流」共用同一個訂閱迴圈,而不必再開一條各自獨立的 POST。
  const subscribe = useCallback((slug: string, title: string, born = false, streamFn: typeof streamCritique = streamCritique) => {
    if (epochs.current.has(slug)) return;      // 同一 slug 已有活訂閱 → 不重複派工
    const epoch = ++seq.current;               // 這條訂閱的身分(永不重用)
    epochs.current.set(slug, epoch);
    const fresh = () => epochs.current.get(slug) === epoch;   // 仍是當前這條?
    (async () => {
      try {
        // born=新孕育 → 帶 fresh:取消時後端可清孤兒。重整重接的既有 Run 不帶(後端已存原值)。
        for await (const ev of streamFn(slug, title, born)) {
          if (!fresh()) return;                // 已被 cancel / 新 begin 取代 → 停手
          if (ev.event === "phase") {
            // preview 不在 STEP 表裡(算 0,被 put 的 Math.max 護住,step 不倒退);
            // 它只宣告「早出 viz 落檔了」→ 孕育中改畫真骨。skip=產失敗,續用象徵骨。
            if (ev.data?.name === "preview") {
              if (ev.data?.status === "ok") put(slug, title, 0, "running", true);
              continue;
            }
            const s = (STEP[ev.data?.name] ?? 0) + (ev.data?.status === "ok" ? 1 : 0);
            put(slug, title, s);
          } else if (ev.event === "done") {
            await onBornRef.current(slug);      // 先刷 index(has_viz 變 true)
            if (fresh()) drop(slug);            // 再移除孕育態 → Catalog 換真實 Skeleton
          } else if (ev.event === "error") {
            if (fresh()) {
              const reason = ev.data?.reason as string | undefined;
              if (reason === "usage-limit") {
                const r = (ev.data.resets_at ?? null) as number | null;
                setUsageLimitResetAt(r);
                saveUsageLimit(r);
                put(slug, title, 0, "paused", undefined, reason, r);      // 不 drop:停在原拍,可續跑
              } else if (reason === "timeout" || reason === "gate" || reason === "crash") {
                put(slug, title, 0, "failed", undefined, reason);         // 不 drop:同上,可續跑/重新分析
              } else {
                drop(slug);                      // cancel 等無可續跑意義:安靜收掉(只有當前這條才動)
              }
            }
          }
        }
      } catch {
        if (fresh()) drop(slug);
      } finally {
        if (epochs.current.get(slug) === epoch) epochs.current.delete(slug);
      }
    })();
  }, []);

  useEffect(() => {
    getRunningCritiques().then(rs => rs.forEach(r => { put(r.slug, r.title, r.step); subscribe(r.slug, r.title); }));
    // 併入 index 裡 resumable 的故事(paused/failed,串流早已斷開):讓停住的星在重整後也畫得出來,
    // 不必等一條活的 Run。只在初載跑一次(不隨 index 變動重跑,避免覆蓋掉正在進行中的訂閱狀態)。
    getIndex().then(idx => {
      for (const e of idx.stories) {
        if (!e.resumable || epochs.current.has(e.slug)) continue;
        put(e.slug, e.title, STEP[e.stage] ?? 0, resumedStatus(e.status));
      }
    }).catch(() => {});
  }, [subscribe]);

  // 到重置時刻自動收掉提示(順手清掉過期持久化);頁面開著跨過 reset 也會自己消失
  useEffect(() => {
    if (typeof usageLimitResetAt !== "number") return;
    const clear = () => { setUsageLimitResetAt(undefined); saveUsageLimit(undefined); };
    const ms = usageLimitResetAt * 1000 - Date.now();
    if (ms <= 0) { clear(); return; }
    const t = window.setTimeout(clear, Math.min(ms, 2_147_483_647));
    return () => window.clearTimeout(t);
  }, [usageLimitResetAt]);

  const begin = useCallback((slug: string, title: string) => { put(slug, title, 1); subscribe(slug, title, true); }, [subscribe]);
  const cancel = useCallback((slug: string) => {
    cancelCritique(slug);
    epochs.current.delete(slug);   // 作廢當前訂閱:其後續事件(含取消 error)不再改狀態
    drop(slug);
  }, []);
  // 續跑:paused/failed 的胚胎重新 POST(不帶 mode)——後端會補播已發事件、跳過已完成階段。
  const resume = useCallback((slug: string, title: string) => {
    put(slug, title, 1, "running");
    subscribe(slug, title, false);
  }, [subscribe]);
  // 重新分析:對已完整的故事重丟一次(帶 mode:"reanalyze");同一個訂閱迴圈換用 reanalyzeCritique
  // 觸發+接流,避免另開一條打到同一端點的 POST。故事未完整時後端 409,由 sseStream 的 !res.ok 拋出
  // → catch 分支 drop(slug);此函式本身是 fire-and-forget,呼叫端要另外提示錯誤得自行 try/catch。
  const reanalyze = useCallback((slug: string, title: string) => {
    put(slug, title, 1, "running");
    subscribe(slug, title, false, reanalyzeCritique);
  }, [subscribe]);

  const dismissUsageLimit = useCallback(() => { setUsageLimitResetAt(undefined); saveUsageLimit(undefined); }, []);
  return { gestations, begin, cancel, resume, reanalyze, usageLimitResetAt, dismissUsageLimit };
}
