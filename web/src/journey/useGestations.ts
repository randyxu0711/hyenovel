import { useCallback, useEffect, useRef, useState } from "react";
import { getRunningCritiques, streamCritique, cancelCritique } from "../data/client";
import type { Gestation } from "../types";

const STEP: Record<string, number> = { analyst: 1, criticizer: 2, render: 3 };

// 獨佔後端孕育狀態:載入時併 /running、逐篇訂閱 SSE 更新 step、done → 誕生(onBorn+移除)。
// 連線斷了不影響後端 Run;重整後靠 /running + 重訂閱把胚胎接回來。
// 每條訂閱帶一個單調遞增 epoch;cancel 或對同 slug 重新 begin 會作廢舊 epoch,使舊串流的殘留
// 事件(如取消 error)不再改狀態 —— 避免 cancel→立即 re-begin 的競態誤刪新胎。
export function useGestations(onBorn: (slug: string) => void | Promise<void>) {
  const [gestations, setGestations] = useState<Map<string, Gestation>>(new Map());
  const [usageLimitResetAt, setUsageLimitResetAt] = useState<number | null | undefined>(undefined);  // undefined=無提示;resets_at(可 null)
  const epochs = useRef<Map<string, number>>(new Map());  // slug -> 當前有效訂閱的 epoch
  const seq = useRef(0);                                    // 全域單調遞增,epoch 永不重用
  const onBornRef = useRef(onBorn);
  onBornRef.current = onBorn;

  const put = (slug: string, title: string, step: number, status = "running") =>
    setGestations(m => {
      const n = new Map(m);
      const cur = n.get(slug);
      n.set(slug, { title: title || cur?.title || slug, status, step: Math.max(step, cur?.step ?? 0) });
      return n;
    });
  const drop = (slug: string) =>
    setGestations(m => { const n = new Map(m); n.delete(slug); return n; });

  const subscribe = useCallback((slug: string, title: string) => {
    if (epochs.current.has(slug)) return;      // 同一 slug 已有活訂閱 → 不重複派工
    const epoch = ++seq.current;               // 這條訂閱的身分(永不重用)
    epochs.current.set(slug, epoch);
    const fresh = () => epochs.current.get(slug) === epoch;   // 仍是當前這條?
    (async () => {
      try {
        for await (const ev of streamCritique(slug, title)) {
          if (!fresh()) return;                // 已被 cancel / 新 begin 取代 → 停手
          if (ev.event === "phase") {
            const s = (STEP[ev.data?.name] ?? 0) + (ev.data?.status === "ok" ? 1 : 0);
            put(slug, title, s);
          } else if (ev.event === "done") {
            await onBornRef.current(slug);      // 先刷 index(has_viz 變 true)
            if (fresh()) drop(slug);            // 再移除孕育態 → Catalog 換真實 Skeleton
          } else if (ev.event === "error") {
            if (fresh()) {
              if (ev.data?.reason === "usage-limit") setUsageLimitResetAt(ev.data.resets_at ?? null);
              drop(slug);                        // 取消/失敗:安靜收掉(只有當前這條才動)
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
  }, [subscribe]);

  const begin = useCallback((slug: string, title: string) => { put(slug, title, 1); subscribe(slug, title); }, [subscribe]);
  const cancel = useCallback((slug: string) => {
    cancelCritique(slug);
    epochs.current.delete(slug);   // 作廢當前訂閱:其後續事件(含取消 error)不再改狀態
    drop(slug);
  }, []);

  return { gestations, begin, cancel, usageLimitResetAt, dismissUsageLimit: () => setUsageLimitResetAt(undefined) };
}
