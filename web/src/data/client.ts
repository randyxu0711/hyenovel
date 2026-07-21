import type { IndexFile, VizData, UsageAggregate, UsageAll } from "../types";

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

export const getIndex = () => getJSON<IndexFile>("/data/index.json");
export const getViz = (slug: string) => getJSON<VizData>(`/data/${slug}/viz.json`);
export const getSource = (slug: string) => getText(`/data/${slug}/source.md`);
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
function parseFrame(frame: string): SSEEvent | null {
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

/** 用 fetch + ReadableStream 讀 SSE(EventSource 不支援 POST,故手刻)。 */
async function* sseStream(url: string, body: unknown): AsyncGenerator<SSEEvent> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
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
      if (ev) yield ev;
    }
  }
}

/** 觸發-或-接上完整 critique 鏈;串 phase 進度,done 後呼叫端應重 fetch viz.json + index。
 *  後端是背景 Run:重整後用同一 slug 再呼一次就會補播已發事件並續播(不會重複派工)。
 *  fresh=這是新孕育(取消時後端可清掉剛 ingest 的孤兒);既有故事再評論不要帶,取消才不會刪 source.md。 */
export const streamCritique = (slug: string, title?: string, fresh = false) =>
  sseStream(`/api/critique/${slug}`, { title: title ?? "", fresh });

/** 重新分析已完成故事:同一個 POST 先觸發後端 reanalyze(snapshot 舊產物、resume_point 重置到 analyst),
 *  再接上同一條 SSE 串流(與 streamCritique 同構,呼叫端一樣 for-await 消費)。
 *  故事未完整時後端回 409,呼叫端自行接。 */
export const reanalyzeCritique = (slug: string, title?: string) =>
  sseStream(`/api/critique/${slug}`, { title: title ?? "", mode: "reanalyze" });

export type RunningCritique = { slug: string; title: string; status: string; step: number };

/** 還在跑的 critique(重整後用來重新接上成形動畫)。 */
export async function getRunningCritiques(): Promise<RunningCritique[]> {
  try {
    const res = await fetch("/api/critique/running");
    if (!res.ok) return [];
    return (await res.json()).running ?? [];
  } catch { return []; }
}

/** 取消進行中的 critique(cancel 背景 Task → 收掉 claude 行程)。 */
export async function cancelCritique(slug: string): Promise<boolean> {
  try {
    const res = await fetch(`/api/critique/${slug}`, { method: "DELETE" });
    return res.ok ? ((await res.json()).cancelled ?? false) : false;
  } catch { return false; }
}

/** 討論一輪;sessionId 為 null = 開新 session(後端在 done.data.session_id 回傳)。
 *  anchors = 這輪在談的 node id;後端落進 transcript.jsonl,將來的召回靠它定位。 */
export const streamDiscuss = (slug: string, sessionId: string | null, message: string, anchors: string[] = []) =>
  sseStream(`/api/discuss/${slug}`, { session_id: sessionId, message, anchors });

/** 上傳檔案抽文字(只抽不寫,給前端預覽改字)。 */
export async function extractStory(file: File): Promise<{ filename: string; text: string; chars: number }> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/stories/extract", { method: "POST", body: fd });
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
