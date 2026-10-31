import { useEffect, useState } from "react";
import { api, DashError } from "./api";

export type Job = { step: string | null; done: boolean; error: DashError | null };
const IDLE: Job = { step: null, done: false, error: null };

/** 跟著一個分析 job 的 SSE:目前哪一步、有沒有收尾。jobId 為 null = 不跟。 */
export function useJob(jobId: number | null): Job {
  const [job, setJob] = useState<{ id: number; v: Job } | null>(null);
  useEffect(() => {
    if (jobId === null) return;
    let live = true;
    const set = (v: Job) => { if (live) setJob({ id: jobId, v }); };
    (async () => {
      try {
        for await (const ev of api.jobEvents(jobId)) {
          if (!live) return;
          if (ev.event === "phase" && ev.data?.status === "start") set({ ...IDLE, step: ev.data.name });
          else if (ev.event === "done") { set({ step: null, done: true, error: null }); return; }
          else if (ev.event === "error") {
            set({ step: null, done: false, error: new DashError(0, ev.data?.reason ?? "unknown") });
            return;
          }
        }
      } catch (e) {
        set({ ...IDLE, error: e instanceof DashError ? e : new DashError(0, "unknown") });
      }
    })();
    return () => { live = false; };
  }, [jobId]);
  return job && job.id === jobId ? job.v : IDLE;
}
