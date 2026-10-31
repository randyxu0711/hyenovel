import { sseFetch, type SSEEvent } from "../data/client";

/** 與 den/app.py 的 ERROR_CODES 一致(加 den-down);den/tests/test_app_errors.py 比對兩份。 */
export const DEN_ERROR_CODES = [
  "bad-slug", "unknown-work", "bad-part", "not-analyzed", "no-notes", "no-feedback",
  "nothing-running", "unknown-session", "busy", "quote-not-in-source", "quote-too-long",
  "empty-story", "story-too-long", "unknown-slug-ref", "file-too-large", "extract-failed",
  "no-runner", "nothing-to-resume", "bad-host", "bad-origin", "bad-token", "bad-launch-code",
  "unknown-character", "unknown-session-id", "ambiguous-session",
  "den-down",
];

export class DashError extends Error {
  constructor(public status: number, public code: string, public params: Record<string, unknown> = {}, detail = "") {
    super(detail || code);
  }
}

export type LText = { "zh-Hant"?: string; en?: string };
export type ColorPair = { fill: string; text: string };
export type Character = {
  id: string; mode: string; name: LText; line: LText;
  avatar: { kind: string; seed: string };
  colors: { light: ColorPair; dark: ColorPair };
  voice: string;
};
export type ThemeTokens = Record<string, string>;
export type Theme = { id: string; name: LText; source: string; light: ThemeTokens; dark: ThemeTokens };

export type Work = { slug: string; title: string; version: number; chars: number; [k: string]: unknown };
export type WorkDetail = {
  slug: string; title: string; version: number; text: string; state: string;
  job_id: number | null; notes_ready: boolean;
};
export type SessionRow = {
  session: string; started_at: number; last_at: number; turns: number;
  character: string | null; mode: string | null; preview: string; version: number | null;
};
export type RecentSession = SessionRow & { slug: string; title: string };
export type Turn = {
  role: string; text: string; ts: number; mode: string | null; character: string | null; quotes: string[];
};
export type Estimate = { seconds: number; output_tokens: number; basis: number };
export type SubmitResult = { slug: string; title: string; version: number; new_version: boolean; reused: boolean };
export type SessionDetail = { session: string; slug: string; title: string; turns: Turn[] };

/** 非 2xx 回應 → DashError(讀 den 的 {detail, code, params})。request 與串流共用。 */
async function throwDashError(res: Response): Promise<never> {
  let body: any = {};
  try { body = await res.json(); } catch { /* 非 JSON 的錯誤 */ }
  throw new DashError(res.status, body.code ?? "unknown", body.params ?? {}, typeof body.detail === "string" ? body.detail : "");
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new DashError(0, "den-down");
  }
  if (!res.ok) await throwDashError(res);
  return res.json() as Promise<T>;
}

const post = (body: unknown): RequestInit => ({
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

/** 非 2xx 由 throwDashError 接手(保留 den 的 code);網路斷(TypeError)→ den-down。 */
async function* stream(url: string, init?: RequestInit): AsyncGenerator<SSEEvent> {
  try {
    yield* sseFetch(url, init, throwDashError);
  } catch (e) {
    if (e instanceof DashError) throw e;
    if (e instanceof TypeError) throw new DashError(0, "den-down");
    throw new DashError(0, "unknown");
  }
}

export const api = {
  works: async () => (await request<{ works: Work[] }>("/api/works")).works,
  work: (slug: string) => request<WorkDetail>(`/api/works/${encodeURIComponent(slug)}`),
  sessions: async (slug: string) =>
    (await request<{ sessions: SessionRow[] }>(`/api/works/${encodeURIComponent(slug)}/sessions`)).sessions,
  session: (session: string) => request<SessionDetail>(`/api/sessions/${encodeURIComponent(session)}`),
  recentSessions: async (limit = 20) =>
    (await request<{ sessions: RecentSession[] }>(`/api/sessions?limit=${limit}`)).sessions,
  characters: () => request<{ characters: Character[]; default: string }>("/api/characters"),
  themes: () => request<{ themes: Theme[]; default: string }>("/api/themes"),
  part: async (slug: string, part: "notes") =>
    (await request<{ text: string }>(`/api/works/${encodeURIComponent(slug)}/${part}`)).text,
  estimate: async (chars: number) =>
    (await request<{ estimate: Estimate | null }>(`/api/estimate?chars=${chars}`)).estimate,
  extract: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ filename: string; text: string; chars: number }>("/api/extract", { method: "POST", body: fd });
  },
  submit: (text: string, title?: string) =>
    request<SubmitResult>("/api/stories", post({ text, title })),
  startJob: (slug: string) => request<{ job_id: number }>("/api/jobs", post({ kind: "critique", slug })),
  jobEvents: (jobId: number) => stream(`/api/jobs/${jobId}/events`),
  /** session 為 null = 開新局(局 id 在 done 事件裡回)。 */
  talk: (slug: string, body: { session: string | null; message: string; character: string; quotes: string[] }) =>
    stream(`/api/discuss/${encodeURIComponent(slug)}`, post({
      session_id: body.session, message: body.message, character: body.character, quotes: body.quotes,
    })),
};
