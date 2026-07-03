import { useCallback, useEffect, useRef, useState } from "react";
import { getRunningCritiques, streamCritique, cancelCritique } from "../data/client";
import type { Gestation } from "../types";

const STEP: Record<string, number> = { analyst: 1, criticizer: 2, render: 3 };

// 獨佔後端孕育狀態:載入時併 /running、逐篇訂閱 SSE 更新 step、done → 誕生(onBorn+移除)。
// 連線斷了不影響後端 Run;重整後靠 /running + 重訂閱把胚胎接回來。
export function useGestations(onBorn: (slug: string) => void | Promise<void>) {
  const [gestations, setGestations] = useState<Map<string, Gestation>>(new Map());
  const active = useRef<Set<string>>(new Set());
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
    if (active.current.has(slug)) return;   // 同一篇只一條訂閱(後端本就防重複派工)
    active.current.add(slug);
    (async () => {
      try {
        for await (const ev of streamCritique(slug, title)) {
          if (ev.event === "phase") {
            const s = (STEP[ev.data?.name] ?? 0) + (ev.data?.status === "ok" ? 1 : 0);
            put(slug, title, s);
          } else if (ev.event === "done") {
            await onBornRef.current(slug);   // 先刷 index(has_viz 變 true)
            drop(slug);                       // 再移除孕育態 → Catalog 換真實 Skeleton
          } else if (ev.event === "error") {
            drop(slug);                       // 取消/失敗:安靜收掉
          }
        }
      } catch { drop(slug); }
      finally { active.current.delete(slug); }
    })();
  }, []);

  useEffect(() => {
    getRunningCritiques().then(rs => rs.forEach(r => { put(r.slug, r.title, r.step); subscribe(r.slug, r.title); }));
  }, [subscribe]);

  const begin = useCallback((slug: string, title: string) => { put(slug, title, 1); subscribe(slug, title); }, [subscribe]);
  const cancel = useCallback((slug: string) => { cancelCritique(slug); drop(slug); }, []);

  return { gestations, begin, cancel };
}
