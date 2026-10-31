import type { IndexFile, IndexEntry, VizData, UsageAggregate, UsageAll, Conclusion, Turn } from "../types";

// ── den 的領域形狀 → 畫面要的 IndexFile(adapter 在 client 這側,den 不綁前端) ──

type DenArtifact = { id: number; created_at: number } | null;
type DenJob = { id: number; state: string; step: string | null; error_class: string | null; updated_at: number };
type DenStory = {
  slug: string; title: string; synopsis: string; nodes: number; edges: number;
  current: { analysis: DenArtifact; feedback: DenArtifact; notes?: DenArtifact }; latest_job: DenJob | null;
};
export type DenStories = { stories: DenStory[] };

function jobView(j: DenJob | null): Pick<IndexEntry, "status" | "stage" | "resumable" | "reason"> {
  if (!j || j.state === "done") return { status: "done", stage: "done", resumable: false, reason: null };
  const stage = j.step ?? "analyst";
  if (j.state === "queued" || j.state === "running") return { status: "running", stage, resumable: false, reason: null };
  if (j.state === "paused") return { status: "paused", stage: j.step ?? "analyst", resumable: true, reason: j.error_class };
  return { status: "failed", stage: j.step ?? "analyst", resumable: true, reason: j.error_class ?? "cancelled" };
}

export function toIndexFile(res: DenStories): IndexFile {
  const stories = res.stories.map((s): IndexEntry => {
    const t = Math.max(s.current.analysis?.created_at ?? 0, s.current.feedback?.created_at ?? 0,
      s.current.notes?.created_at ?? 0, s.latest_job?.updated_at ?? 0);
    return {
      slug: s.slug, title: s.title, synopsis: s.synopsis, nodes: s.nodes, edges: s.edges,
      has_viz: s.current.analysis != null, has_feedback: s.current.feedback != null || s.current.notes != null,
      updated: new Date(t * 1000).toISOString(), ...jobView(s.latest_job),
    };
  });
  return { generated: new Date().toISOString(), count: stories.length, stories };
}

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`讀不到 ${url}(${res.status})`);
  return (await res.json()) as T;
}
async function getText(url: string): Promise<string> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`讀不到 ${url}(${res.status})`);
  return res.text();
}

export const getIndex = async () => toIndexFile(await getJSON<DenStories>("/api/stories"));
export const getViz = (slug: string) => getJSON<VizData>(`/api/stories/${slug}/viz`);
export const getSource = (slug: string) => getText(`/api/stories/${slug}/source`);
export const getConclusions = (slug: string) =>
  getJSON<{ conclusions: Conclusion[] }>(`/api/stories/${slug}/conclusions`);
/** 這篇的討論逐字歷史。F5 之後畫面靠它接回來 —— 正本一直在 DB 裡。 */
export const getTranscript = (slug: string) =>
  getJSON<{ turns: Turn[] }>(`/api/stories/${slug}/transcript`);
export const getUsage = (slug: string) => getJSON<UsageAggregate>(`/api/usage/${slug}`);
export const getUsageAll = () => getJSON<UsageAll>("/api/usage");
export async function getStory(slug: string): Promise<{ viz: VizData; source: string }> {
  const [viz, source] = await Promise.all([
    getViz(slug),
    getSource(slug),
  ]);
  return { viz, source };
}

// ── L4 後端(B 方案)邊界:靜態 fetch 以上不動,以下是動態後端 ────────────

export type SSEEvent = { event: string; data: any };

/** 解析一個 SSE frame(event: / data: 多行);無 data 回 null。 */
export function parseFrame(frame: string): SSEEvent | null {
  let event = "message";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return { event, data };
  }
}

/** den 的 frame 沒有 event: 行,事件名在 JSON 裡({event,data});解包成呼叫端一直拿到的形狀。 */
function unwrap(ev: SSEEvent): SSEEvent {
  const d = ev.data;
  if (ev.event === "message" && d && typeof d === "object" && typeof d.event === "string" && "data" in d) {
    const inner: SSEEvent = { event: d.event, data: d.data };
    // den 對「已結束的 job」不重播,只送 state 現況;翻成呼叫端認得的收尾事件。
    if (inner.event === "state") {
      const st = inner.data ?? {};
      if (st.state === "done") return { event: "done", data: { ok: true } };
      if (st.state === "paused" || st.state === "failed" || st.state === "cancelled")
        return { event: "error", data: {
          reason: st.error_class ?? "cancelled", message: st.detail?.message ?? "",
          resets_at: st.detail?.resets_at ?? null,       // useGestations 讀頂層 resets_at
        } };
    }
    return inner;
  }
  return ev;
}

/** 用 fetch + ReadableStream 讀 SSE(EventSource 不支援 POST,故手刻)。POST / GET 共用。 */
export async function* sseFetch(url: string, init?: RequestInit): AsyncGenerator<SSEEvent> {
  const res = await fetch(url, init);
  if (!res.ok || !res.body) throw new Error(`${url}(${res.status})`);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const ev = parseFrame(frame);
      if (ev) yield unwrap(ev);
    }
  }
}

const sseStream = (url: string, body: unknown) =>
  sseFetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });

/** 送一個 critique job(den 對同一篇已有進行中的 job 會回既有的,不重複派工),再串它的事件。
 *  title / fresh 保留簽名但不送:title 由 analyst 定,取消不刪故事。 */
async function* critiqueJob(slug: string): AsyncGenerator<SSEEvent> {
  const res = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind: "critique", slug }),
  });
  if (!res.ok) throw new Error(`/api/jobs(${res.status})`);
  const { job_id } = await res.json();
  yield* sseFetch(`/api/jobs/${job_id}/events`);
}

/** 觸發-或-接上完整 critique 鏈;串 phase 進度,done 後呼叫端應重 fetch viz + index。 */
export const streamCritique = (slug: string, _title?: string, _fresh = false) => critiqueJob(slug);

/** 重新分析:den 的 job 本身就是從頭或續跑,與 streamCritique 同構。 */
export const reanalyzeCritique = (slug: string, _title?: string) => critiqueJob(slug);

export type RunningCritique = { slug: string; title: string; status: string; step: number };

/** 還在跑的 critique(重整後用來重新接上成形動畫)。den 是唯一真相,每次現查。 */
export async function getRunningCritiques(): Promise<RunningCritique[]> {
  try {
    const res = await fetch("/api/stories");
    if (!res.ok) return [];
    const { stories } = (await res.json()) as DenStories;
    return stories
      .filter(s => s.latest_job && (s.latest_job.state === "queued" || s.latest_job.state === "running"))
      .map(s => ({
        slug: s.slug, title: s.title, status: "running",
        step: ({ analyst: 1, criticizer: 2, reviewer: 2 } as Record<string, number>)[s.latest_job!.step ?? ""] ?? 0,
      }));
  } catch { return []; }
}

/** 取消進行中的 critique:現查該篇 latest_job,進行中才打 cancel。 */
export async function cancelCritique(slug: string): Promise<boolean> {
  try {
    const res = await fetch("/api/stories");
    if (!res.ok) return false;
    const { stories } = (await res.json()) as DenStories;
    const j = stories.find(s => s.slug === slug)?.latest_job;
    if (!j || (j.state !== "queued" && j.state !== "running")) return false;
    return (await fetch(`/api/jobs/${j.id}/cancel`, { method: "POST" })).ok;
  } catch { return false; }
}

/** 討論一輪;sessionId 為 null = 開新 session(後端在 done.data.session_id 回傳)。
 *  anchors = 這輪在談的 node id;後端落進 den DB(utterance.anchors),將來的召回靠它定位。 */
export const streamDiscuss = (slug: string, sessionId: string | null, message: string, anchors: string[] = []) =>
  sseStream(`/api/discuss/${slug}`, { session_id: sessionId, message, anchors });

// 收束沒有前端入口;收束暫無,另開切片。

/** 上傳檔案抽文字(只抽不寫,給前端預覽改字)。 */
export async function extractStory(file: File): Promise<{ filename: string; text: string; chars: number }> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/extract", { method: "POST", body: fd });
  if (!res.ok) throw new Error(`抽文字失敗(${res.status})`);
  return res.json();
}

/** 確認後落 source.md,回新 slug(接著可 streamCritique 那個 slug)。 */
export async function createStory(title: string, text: string): Promise<{ slug: string }> {
  const res = await fetch("/api/stories", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, text }),
  });
  if (!res.ok) throw new Error(`建立故事失敗(${res.status})`);
  return res.json();
}
