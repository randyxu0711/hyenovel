import { useEffect, useState } from "react";
import { api, DashError } from "./api";

/** analysed = 這次訂閱期間收到 analyst 那一步 commit 完成(續跑時略過的 resume-skip 不算)。 */
export type Job = { step: string | null; done: boolean; error: DashError | null; analysed: boolean };
const TERMINAL = ["done", "paused", "failed", "cancelled"];
const IDLE: Job = { step: null, done: false, error: null, analysed: false };

/** 跟著一個分析 job 的 SSE:目前哪一步、有沒有收尾。jobId 為 null = 不跟。 */
export function useJob(jobId: number | null): Job {
  const [job, setJob] = useState<{ id: number; v: Job } | null>(null);
  useEffect(() => {
    if (jobId === null) return;
    let live = true;
    let analysed = false;
    const set = (v: Omit<Job, "analysed">) => { if (live) setJob({ id: jobId, v: { ...v, analysed } }); };
    (async () => {
      try {
        let step: string | null = null;
        for await (const ev of api.jobEvents(jobId)) {
          if (!live) return;
          if (ev.event === "phase" && ev.data?.status === "start") { step = ev.data.name; set({ step, done: false, error: null }); }
          else if (ev.event === "phase" && ev.data?.name === "analyst" && ev.data?.status === "ok" && ev.data?.detail !== "resume-skip") {
            analysed = true; set({ step, done: false, error: null });
          } else if (ev.event === "state" && TERMINAL.includes(ev.data?.state)) {
            set(ev.data.state === "done" ? { step: null, done: true, error: null }
              : { step: null, done: false, error: new DashError(0, ev.data.error_class ?? ev.data.state) });
            return;
          } else if (ev.event === "done") { set({ step: null, done: true, error: null }); return; }
          else if (ev.event === "error") {
            set({ step: null, done: false, error: new DashError(0, ev.data?.reason ?? "unknown") });
            return;
          }
        }
        set({ step: null, done: true, error: null });   // 串流沒收尾就結束:當作結束,讓呼叫端重抓真實狀態
      } catch (e) {
        set({ step: null, done: false, error: e instanceof DashError ? e : new DashError(0, "unknown") });
      }
    })();
    return () => { live = false; };
  }, [jobId]);
  return job && job.id === jobId ? job.v : IDLE;
}
